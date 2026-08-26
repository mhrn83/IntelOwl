import requests

from django.conf import settings

from api_app.ingestors_manager.classes import Ingestor
from api_app.ingestors_manager.exceptions import (
    IngestorConfigurationException,
    IngestorRunException,
)


class CustomGreedyBear(Ingestor):
    """
    Customized Intelowl ingestor for fetching IOCs
    from the greedybear intelowl_export endpoint.
    """
    base_url: str
    _api_key: str
    lookback_minutes: int = 30

    def run(self):
        if self.lookback_minutes <= 0:
            raise IngestorConfigurationException(
                f'Invalid lookback_minutes: {self.lookback_minutes}. Must be a positive integer.'
            )

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
