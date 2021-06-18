# -*- coding: utf-8 -*-
"""
WooCommerce API Class
"""
import requests

__title__ = "wc-api"
__version__ = "1.2.1"
__author__ = "Claudio Sanches @ WooThemes"
__license__ = "MIT"

from requests import request
from json import dumps as jsonencode
from .oauth import OAuth


class API(object):
    """ API Class """

    def __init__(self, url, consumer_key, consumer_secret, **kwargs):
        self.url = url
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.wp_api = kwargs.get("wp_api", False)
        self.version = kwargs.get("version", "v3")
        self.is_ssl = self.__is_ssl()
        self.timeout = kwargs.get("timeout", 3600)
        self.verify_ssl = kwargs.get("verify_ssl", True)
        self.query_string_auth = kwargs.get("query_string_auth", False)

    def __is_ssl(self):
        """ Check if url use HTTPS """
        return self.url.startswith("https")

    def __get_url(self, endpoint):
        """ Get URL for requests """
        url = self.url
        api = "wc-api"

        if url.endswith("/") is False:
            url = "%s/" % url

        if self.wp_api:
            api = "wp-json"

        return "%s%s/%s/%s" % (url, api, self.version, endpoint)

    def __get_oauth_url(self, url, method):
        """ Generate oAuth1.0a URL """
        oauth = OAuth(
            url=url,
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            version=self.version,
            method=method
        )

        return oauth.get_oauth_url()

    def __request(self, method, endpoint, data, wc_job=None):
        """ Do requests """
        url = self.__get_url(endpoint)
        auth = None
        params = {}
        headers = {
            "user-agent": "WooCommerce API Client-Python/%s" % __version__,
            "accept": "application/json"
        }

        if self.is_ssl is True and self.query_string_auth is False:
            auth = (self.consumer_key, self.consumer_secret)
        elif self.is_ssl is True and self.query_string_auth is True:
            params = {
                "consumer_key": self.consumer_key,
                "consumer_secret": self.consumer_secret
            }
        else:
            url = self.__get_oauth_url(url, method)
        req_data = data
        if data is not None:
            data = jsonencode(data, ensure_ascii=False).encode('utf-8')
            headers["content-type"] = "application/json;charset=utf-8"

        response = request(
            method=method,
            url=url,
            verify=self.verify_ssl,
            auth=auth,
            params=params,
            data=data,
            timeout=self.timeout,
            headers=headers
        )
        if not isinstance(response, requests.models.Response):
            wc_job.env['wc.process.job.cft.line'].create(
                {'wc_job_id': wc_job.id, 'message': "WooCommerce Response is not in proper format"})
            vals = {}
            data and vals.update({'wc_request': data.decode("utf-8")})
            vals.update({'wc_response': response.text})
            vals and wc_job.write(vals)
            return False
        try:
            response.json()
        except Exception as e:
            wc_job.env['wc.process.job.cft.line'].create({'wc_job_id': wc_job.id,
                                                          'message': "WooCommerce Response can\'t convert in JSON, Due to that operation can\'t process ahead\n Error: %s" % (
                                                              e)})
            vals = {}
            data and vals.update({'wc_request': data.decode("utf-8")})
            vals.update({'wc_response': response.text})
            vals and wc_job.write(vals)
            return False
        if response.status_code not in [200, 201, 400]:
            message = "Process not completed, Reason: \n%s" % (response.text)
            wc_job.env['wc.process.job.cft.line'].create(
                {'wc_job_id': wc_job.id, 'message': message})
            vals = {}
            data and vals.update({'wc_request': data.decode("utf-8")})
            vals.update({'wc_response': response.text})
            vals and wc_job.write(vals)
            return False
        if endpoint not in ['products/categories', 'products/tags',
                            'products/attributes'] and response.status_code == 400:
            if endpoint in ['products', 'products/batch']:
                message = "Export product {0} error: {1}".format(req_data.get('name'), response.text)
            else:
                message = response.text
            wc_job.env['wc.process.job.cft.line'].create(
                {'wc_job_id': wc_job.id, 'message': message})
            vals = {}
            data and vals.update({'wc_request': data.decode("utf-8")})
            vals.update({'wc_response': response.text})
            vals and wc_job.write(vals)
            return False
        vals = {}
        if data:
            wc_request = wc_job.wc_request and wc_job.wc_request + "\n" + data.decode("utf-8") or data.decode("utf-8")
            vals.update({'wc_request': wc_request})
        response and vals.update({'wc_response': "Response format is Okay"})
        vals and wc_job.write(vals)
        return response

    def get(self, endpoint, wc_job=None):
        """ Get requests """
        return self.__request("GET", endpoint, None, wc_job=wc_job)

    def post(self, endpoint, data, wc_job=None):
        """ POST requests """
        return self.__request("POST", endpoint, data, wc_job=wc_job)

    def put(self, endpoint, data, wc_job=None):
        """ PUT requests """
        return self.__request("PUT", endpoint, data, wc_job=wc_job)

    def delete(self, endpoint, wc_job=None):
        """ DELETE requests """
        return self.__request("DELETE", endpoint, None, wc_job=wc_job)

    def options(self, endpoint, wc_job=None):
        """ OPTIONS requests """
        return self.__request("OPTIONS", endpoint, None, wc_job=wc_job)
