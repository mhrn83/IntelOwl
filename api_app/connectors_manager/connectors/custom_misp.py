import pymisp
from django.conf import settings

from api_app.mixins import MISPMixin
from api_app.choices import Classification
from api_app.connectors_manager.classes import CTIConnector
from api_app.connectors_manager.exceptions import ConnectorRunException

INTELOWL_MISP_OBJECT_TYPE_MAP = {
    Classification.IP: 'domain-ip',
    Classification.DOMAIN: 'domain-ip',
    Classification.HASH: 'malware',
    Classification.URL: 'url',
}


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

    def _attach_galaxy(self, misp_entity: pymisp.MISPEvent | pymisp.MISPAttribute,
                       galaxy_name: str, cluster_name: str):
        """Find and attach a cluster to the misp entity."""
        if not cluster_name:
            return

        galaxies = self.misp.search_galaxy(value=galaxy_name, pythonify=True)
        if galaxies:
            clusters = self.misp.search_galaxy_clusters(
                galaxies[0], searchall=cluster_name, pythonify=True)
            if clusters:
                self.misp.attach_galaxy_cluster(misp_entity, clusters[0])

    def _handle_vt_report(self, event: pymisp.MISPEvent, report: dict):
        """Enrich MISP event using VirusTotal report."""
        _, vt_object = self.find_object_attr(
            event, report['link'], 'virustotal-report')
        if vt_object:
            return

        attrs = report['data']['attributes']
        ref_attr, ref_object = self.find_object_attr(
            event, self.observable_value,
            INTELOWL_MISP_OBJECT_TYPE_MAP.get(self.classification)
        )
        positives, total = self.__calculate_detection_ratio(
            attrs.get('last_analysis_stats', {}))
        vt_attributes = [('permalink', report['link']),
                         ('detection-ratio', f'{positives}/{total}'),
                         ('community-score', attrs.get('reputation', 0))]

        self.handle_event_object(
            event, '', 'virustotal-report', 'analysis-for', 'VirusTotal report',
            ref_object, vt_attributes, ref_dir=-1, standalone=False
        )

        aliases = []
        aliases.append(attrs.get('sha1', ''))
        aliases.append(attrs.get('md5', ''))
        aliases.append(attrs.get('vhash', ''))
        aliases.append(attrs.get('tlsh', ''))
        aliases.append(attrs.get('ssdeep', ''))
        aliases += attrs.get('names', [])
        ref_object.add_attributes('alias', *aliases)

        magic = attrs.get('magic', '')
        if magic:
            ref_object.add_attribute('architecture_execution_env', magic)

        jarm = attrs.get('jarm', '')
        if jarm:
            self.handle_event_object(
                event, jarm, 'jarm', 'has', 'IP address JARM hash',
                ref_object, [('jarm', jarm)]
            )

        whois = attrs.get('whois', '')
        if whois:
            self.handle_event_object(
                event, whois,
                'whois', 'describes', 'whois information',
                ref_object, [('text', whois)],
                ref_dir=-1, standalone=False
            )

        ai_analysis_results = attrs.get('crowdsourced_ai_results', [])
        for result in ai_analysis_results:
            self.handle_event_object(
                event, '', 'malware-analysis', 'verdicts', 'A verdict from crowdsourced AI',
                ref_object, [('product', 'AI crowdsourced analysis'),
                             ('result', result.get('verdict', 'unknown'))],
                ref_dir=-1, standalone=False
            )

        yara_results = attrs.get('crowdsourced_yara_results', [])
        for yara in yara_results:
            rule_name = yara.get('rule_name')
            self.handle_event_object(
                event, rule_name,
                'yara', 'matches', 'YARA matches for the malware',
                ref_object, [('yara-rule-name', rule_name),
                             ['reference', yara.get('source', '')]],
            )

        self._attach_galaxy(ref_attr, 'Country', attrs.get('country', ''))

        for tag in attrs.get('tags', []):
            ref_attr.add_tag(f'virusTotal:generic={tag}')

        for tag in attrs.get('type_tags', []):
            ref_attr.add_tag(f'virusTotal:file-type={tag}')

        cls = attrs.get('popular_threat_classification', {})
        for category in cls.get('popular_threat_category', []):
            ref_attr.add_tag(
                f'malware_classification:malware-category={category.get("value").title()}')

    def run(self):
        try:
            self.misp = pymisp.PyMISP(
                url=self.url,
                key=self._auth_key,
                ssl=False,
                tool='IntelOwl-Connector'
            )
        except Exception as e:
            raise ConnectorRunException(
                f'MISP initialization failed: {str(e)}')

        event = self.find_misp_event(self.observable_value)
        if not event:
            raise ConnectorRunException(
                f'MISP event with attribute {self.observable_value} not found.')

        for report in self._job.analyzerreports.all():
            if report.status != 'SUCCESS':
                continue

            analyzer_name = report.config.name
            _report = report.report

            if 'VirusTotal' in analyzer_name:
                self._handle_vt_report(event, _report)

        try:
            self.misp.update_event(event)
        except Exception as e:
            raise ConnectorRunException(f'Event update failed: {str(e)}')

        return self.misp.get_event(event.id)

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
