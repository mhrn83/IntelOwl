import pymisp
from django.conf import settings

from api_app.mixins import MISPMixin
from api_app.connectors_manager.classes import CTIConnector
from api_app.connectors_manager.exceptions import ConnectorRunException


class CustomMISP(CTIConnector, MISPMixin):
    """Customized MISP connector."""
    url: str
    _auth_key: str

    def __calculate_detection_ratio(self, stats: dict) -> tuple:
        """"""
        excluded = {'type-unsupported', 'timeout',
                    'confirmed-timeout', 'failure'}

        positives = stats.get('malicious', 0)
        total = sum(v for k, v in stats.items() if k not in excluded)

        return (positives, total)

    def _add_virustotal_object(self, event: pymisp.MISPEvent, report: dict):
        """Build a VT MISP object and add it to the MISP event."""
        vt_report = pymisp.MISPObject(
            name='virustotal-report',
            strict=True,
            standalone=False
        )

        attrs = report['data']['attributes']
        attr_id = self.find_attr_id(event, self.observable_value)
        positives, total = self.__calculate_detection_ratio(
            attrs.get('last_analysis_stats', {}))

        vt_report.add_attribute('permalink', report['link'])
        vt_report.add_attribute('detection-ratio', f'{positives}/{total}')
        vt_report.add_attribute('community-score', attrs.get('reputation', 0))
        vt_report.add_reference(
            referenced_uuid=attr_id,
            relationship_type='analysis-for',
            comment='VirusTotal report'
        )

        event.add_object(vt_report)

    def run(self):
        try:
            misp_instance = pymisp.PyMISP(
                url=self.url,
                key=self._auth_key,
                ssl=False,
                tool='IntelOwl-Connector'
            )
        except Exception as e:
            raise ConnectorRunException(
                f'MISP initialization failed: {str(e)}')

        event = self.find_misp_event(misp_instance, self.observable_value)
        if not event:
            raise ConnectorRunException(
                f'MISP event with attribute {self.observable_value} not found.')

        for report in self._job.analyzerreports.all():
            if report.status != 'SUCCESS':
                continue

            analyzer_name = report.config.name
            _report = report.report

            if 'VirusTotal' in analyzer_name:
                self._add_virustotal_object(event, _report)

        try:
            misp_instance.update_event(event)
        except Exception as e:
            raise ConnectorRunException(f'Event update failed: {str(e)}')

        return misp_instance.get_event(event.id)

    def health_check(self, user=None) -> tuple:
        if settings.STAGE_CI or settings.MOCK_CONNECTIONS:
            return True, 'Mock connection successful'

        params = self._config.parameters.annotate_configured(self._config, user).annotate_value_for_user(
            self._config, user
        )

        url = key = None
        for param in params:
            if param.name == 'base_url':
                url = param.value
            elif param.name == 'api_key':
                key = param.value

        if not url:
            return False, 'Missing config base url'
        if not key:
            return False, 'Missing config api key'

        try:
            misp = pymisp.PyMISP(
                url=url,
                key=key,
                ssl=False,
                tool='IntelOwl-Connector'
            )

            misp.misp_instance_version
            return True, 'Connected successfully'
        except Exception as e:
            return False, f'Connection failed: {str(e)}'
