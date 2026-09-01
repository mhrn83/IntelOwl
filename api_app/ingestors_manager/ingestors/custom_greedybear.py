import requests

from django.conf import settings
import pymisp

from api_app.ingestors_manager.classes import Ingestor
from api_app.choices import Classification
from api_app.mixins import MISPMixin
from api_app.ingestors_manager.exceptions import (
    IngestorConfigurationException,
    IngestorRunException,
)

GREEDYBEAR_INTELOWL_TYPE_MAP = {
    'ip': Classification.IP,
    'domain': Classification.DOMAIN
}


class CustomGreedyBear(Ingestor, MISPMixin):
    """
    Customized Intelowl ingestor for fetching IOCs
    from the greedybear intelowl_export endpoint.
    """
    base_url: str
    _api_key: str
    lookback_minutes: int = 30

    misp_url: str
    _misp_key: str
    misp: pymisp.PyMISP
    cmd_object_template: dict = dict()

    @property
    def _command_set_object_template(self) -> dict:
        """Gets *command-set* object template from MISP instance."""
        if self.cmd_object_template:
            return self.cmd_object_template

        self.cmd_object_template = self.misp.get_raw_object_template(
            'command-set')
        return self.cmd_object_template

    def _handle_event_attribute(self, event: pymisp.MISPEvent, attr: tuple):
        """
        Adds a non-existing attribute to the event
        or adds sighting on the existing attribute.
        """
        attr_value, _ = attr
        attr_id = self.find_attr_id(event, attr_value)
        if not attr_id:
            self.add_misp_event_attr(event, attr)
        else:
            self.add_attribute_sighting(self.misp, attr_id)

    def _handle_event_command_object(self, event: pymisp.MISPEvent, base_attr_id: str, command_data: tuple):
        """
        Sights an existing *command-set* object
        in the event or creates a new one.
        """
        command_hash, commands = command_data
        attr_id = self.find_attr_id(event, command_hash)
        if attr_id:
            self.add_attribute_sighting(self.misp, attr_id)
            return

        command_set_object = pymisp.MISPObject(
            name='command-set',
            strict=True,
            standalone=False,
            misp_objects_template_custom=self._command_set_object_template
        )

        command_set_object.add_attribute('command-hash', command_hash)

        for command in commands:
            command_set_object.add_attribute('command', command)

        command_set_object.add_reference(
            referenced_uuid=base_attr_id,
            relationship_type='commands-executed-by',
            comment='Commands executed during a session'
        )

        event.add_object(command_set_object)

    def _misp_event_handler(self, data: dict):
        """Get a MISP event and then add attributes and tags."""
        base_attr = (data['source'], GREEDYBEAR_INTELOWL_TYPE_MAP.get(
            data['type'], Classification.GENERIC))
        try:
            event = self.get_misp_event(self.misp, base_attr)
        except Exception as e:
            raise IngestorRunException(
                f'Failed to create/find MISP event: {str(e)}')

        if event is None:
            raise IngestorRunException('Failed to create/find MISP event')

        base_attr_id = self.find_attr_id(event, data['source'])
        base_attr_tags = event.get_attribute_tag(base_attr_id)

        for entry in data['firehol_categories']:
            exists = any(entry in tag.name for tag in base_attr_tags)
            if not exists:
                event.add_tag(f'firehol:list={entry}')

        for hash in data['malwares_shasum']:
            self._handle_event_attribute(
                event, (hash, Classification.HASH))

        for command_data in data['commands'].items():
            self._handle_event_command_object(
                event, base_attr_id, command_data)

        for url in data['downloaded_urls']:
            self._handle_event_attribute(
                event, (url, Classification.URL))

        try:
            self.misp.update_event(event)
        except Exception as e:
            raise IngestorRunException(f'Event update failed: {str(e)}')

    def run(self):
        if self.lookback_minutes <= 0:
            raise IngestorConfigurationException(
                f'Invalid lookback_minutes: {self.lookback_minutes}. Must be a positive integer.'
            )

        try:
            self.misp = pymisp.PyMISP(
                url=self.misp_url,
                key=self._misp_key,
                ssl=False
            )
        except Exception as e:
            raise IngestorRunException(f'MISP initialization failed: {str(e)}')

        req_url = f'{self.base_url.rstrip("/")}/api/intelowl_export/'
        param = {'lookback_minutes': self.lookback_minutes}
        header = {'Authorization': f'Token {self._api_key}'}

        try:
            response = requests.get(req_url, params=param, headers=header)
            response.raise_for_status()
            content = response.json()
        except:
            raise IngestorRunException('Failed to fetch data from GreedyBear')

        cowrie_events = content['cowrie']
        if not isinstance(cowrie_events, list):
            raise IngestorRunException('Unexpected response payload format.')

        for event in cowrie_events:
            self._misp_event_handler(event)

            yield event['source']
            for shasum in event['malwares_shasum']:
                yield shasum
            for url in event['downloaded_urls']:
                yield url

    def health_check(self, user=None) -> tuple:
        if settings.STAGE_CI or settings.MOCK_CONNECTIONS:
            return True, 'Mock connection successful'

        params = self._config.parameters.annotate_configured(self._config, user).annotate_value_for_user(
            self._config, user
        )

        base_url = None
        api_key = None
        lookback_time = 30

        for param in params:
            if param.name == 'base_url':
                base_url = param.value
            elif param.name == 'api_key':
                api_key = param.value
            elif param.name == 'lookback_minutes':
                lookback_time = param.value

        if not base_url or not api_key or lookback_time <= 0:
            return False, 'Missing or bad config parameters'

        req_url = f'{base_url.rsplit("/")}/api/health/'
        header = {'Authorization': f'Token {api_key}'}

        try:
            response = requests.get(req_url, headers=header)
            response.raise_for_status()
            content = response.json()
        except Exception as e:
            return False, f'Connection failed {(str(e))}'

        if content['system'].get('qcluster') != 'up':
            return False, 'Greedybear is down'

        return True, 'Connected successfully'
