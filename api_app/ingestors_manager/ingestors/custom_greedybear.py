import requests

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
