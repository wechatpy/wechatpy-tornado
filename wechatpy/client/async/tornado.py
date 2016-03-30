# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import time

from six.moves.urllib.parse import urlencode
from tornado.gen import coroutine, Return
from tornado.httpclient import AsyncHTTPClient, HTTPRequest

from wechatpy._compat import json
from wechatpy.utils import to_binary
from wechatpy.client import WeChatClient
from wechatpy.exceptions import WeChatClientException


class AsyncClientMixin(object):
    """
    基于 Tornado coroutine 和 ``tornado.httpclient.AsyncHTTPClient`` 的
    异步主动调用客户端实现 mixin

    主要是替换了使用 ``requests`` 实现同步客户端的 ``_request`` 和
     `` _decode_result`` 方法以适应 AsyncHTTPClient 和 requests 的不同。
    """

    @coroutine
    def _request(self, method, url_or_endpoint, **kwargs):
        http_client = AsyncHTTPClient()
        if not url_or_endpoint.startswith(('http://', 'https://')):
            api_base_url = kwargs.pop('api_base_url', self.API_BASE_URL)
            url = '{base}{endpoint}'.format(
                base=api_base_url,
                endpoint=url_or_endpoint
            )
        else:
            url = url_or_endpoint

        headers = {}
        params = kwargs.pop('params', {})
        if 'access_token' not in params:
            # 这里需要针对 tornado 特殊处理
            access_token = self.access_token
            if access_token:
                if not self.expires_at:
                    # user provided access_token, just return it
                    access_token = self.access_token
                else:
                    timestamp = time.time()
                    if self.expires_at - timestamp > 60:
                        access_token = self.access_token
            else:
                # fetch access
                yield self._fetch_access_token()

            params['access_token'] = self.access_token

        params = urlencode(dict((k, to_binary(v)) for k, v in params.items()))
        url = '{0}?{1}'.format(url, params)

        data = kwargs.get('data', {})
        files = kwargs.get('files')
        if files:
            from requests.models import RequestEncodingMixin
            from requests.utils import super_len

            body, content_type = RequestEncodingMixin._encode_files(
                files,
                data
            )
            headers['Content-Type'] = content_type
            headers['Content-Length'] = super_len(body)
        else:
            if isinstance(data, dict):
                body = json.dumps(data, ensure_ascii=False)
                body = body.encode('utf-8')
            else:
                body = data

        result_processor = kwargs.pop('result_processor', None)
        timeout = kwargs.get('timeout', self.timeout)
        req = HTTPRequest(
            url=url,
            method=method.upper(),
            headers=headers,
            body=body if method.upper() != "GET" else None,
            request_timeout=timeout
        )
        res = yield http_client.fetch(req)
        if res.error is not None:
            raise WeChatClientException(
                errcode=None,
                errmsg=None,
                client=self,
                request=req,
                response=res
            )

        result = self._handle_result(
            res, method, url, result_processor, **kwargs
        )
        raise Return(result)

    def _decode_result(self, res):
        try:
            result = json.loads(res.body)
        except (TypeError, ValueError):
            # Return origin response object if we can not decode it as JSON
            return res
        return result

    @property
    def access_token(self):
        return self.session.get(self.access_token_key)

    @coroutine
    def _fetch_access_token(self, url, params):
        """
        替代 requests 版本 _fetch_access_token
        """
        http_client = AsyncHTTPClient()
        params = urlencode(dict((k, to_binary(v)) for k, v in params.items()))
        _url = '{0}?{1}'.format(url, params)

        req = HTTPRequest(
            url=_url,
            method="GET",
            request_timeout=self.timeout
        )
        res = yield http_client.fetch(req)
        if res.error is not None:
            raise WeChatClientException(
                errcode=None,
                errmsg=None,
                client=self,
                request=req,
                response=res
            )

        result = self._decode_result(res)

        if 'errcode' in result and result['errcode'] != 0:
            raise WeChatClientException(
                result['errcode'],
                result['errmsg'],
                client=self,
                request=res.request,
                response=res
            )

        expires_in = 7200
        if 'expires_in' in result:
            expires_in = result['expires_in']
        self.session.set(
            self.access_token_key,
            result['access_token'],
            expires_in
        )
        self.expires_at = int(time.time()) + expires_in
        raise Return(result)

    @coroutine
    def fetch_access_token(self):
        """
        替代 requests 版本 fetch_access_token
        """
        res = yield self._fetch_access_token(
            url='https://api.weixin.qq.com/cgi-bin/token',
            params={
                'grant_type': 'client_credential',
                'appid': self.appid,
                'secret': self.secret
            }
        )
        raise Return(res)


class AsyncWeChatClient(AsyncClientMixin, WeChatClient):
    pass
