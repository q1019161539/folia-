import unittest
import httpx
from publishing import BililiveToolClient,PublishPrepareError,PublishRetryableError


class CollectionClientTests(unittest.TestCase):
    def client(self,body,status=200):
        def respond(request):
            self.assertEqual(request.headers['Authorization'],'secret')
            self.assertNotIn('secret',str(request.url))
            self.assertEqual(request.method,'GET')
            return httpx.Response(status,json=body)
        return BililiveToolClient('http://bili/api','secret',transport=httpx.MockTransport(respond))

    def test_capability_and_strict_response_identity(self):
        client=self.client({'version':1,'durable':True})
        try:self.assertEqual(client.collection_capabilities()['version'],1)
        finally:client.close()
        result={'uid':1,'aid':123,'status':'retry'}
        client=self.client(result)
        try:self.assertEqual(client.collection_job('123',1),result)
        finally:client.close()
        for result in ({'uid':2,'aid':123,'status':'joined'},{'uid':1,'aid':456,'status':'joined'},{'uid':1,'aid':123,'status':'unknown'}):
            client=self.client(result)
            try:
                with self.assertRaises(PublishPrepareError):client.collection_job('123',1)
            finally:client.close()

    def test_missing_retry_and_auth_failure_are_distinct(self):
        for status,expected in ((404,None),(500,PublishRetryableError),(403,PublishPrepareError)):
            client=self.client({},status)
            try:
                if expected is None:self.assertIsNone(client.collection_job('123',1))
                else:
                    with self.assertRaises(expected):client.collection_job('123',1)
            finally:client.close()
