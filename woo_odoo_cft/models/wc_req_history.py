from odoo import fields, models, api
import pytz
from datetime import datetime
import json


class wc_req_res(models.Model):
    _name = 'wc.req.history'
    _rec_name = 'wc_instance_id'
    _order = 'create_date desc'
    url = fields.Text('URL')
    type = fields.Many2one('wc.req.type', string='Type')
    req = fields.Text('Request')
    res = fields.Text('Response')
    req_time = fields.Char("Request Time", readonly="1")
    res_time = fields.Char("Response Time", readonly="1")
    wc_instance_id = fields.Many2one('wc.instance', string='WooCommerce Instance')

    def req_res_data(self, method, url, verify_ssl, auth, params, data, timeout, headers, res, req_time, res_time):
        wc_instance_obj = self.env['wc.instance']
        wc_req_type_obj = self.env['wc.req.type']
        website_url = ""
        if url.__contains__('wc-api'):
            website_url = url.split('wc-api')[0][:-1]
        if url.__contains__('wp-json'):
            website_url = url.split('wp-json')[0][:-1]
        if website_url:
            wc_instance = wc_instance_obj.search([('website_url', '=', website_url)], limit=1)
            if not wc_instance:
                wc_instance = wc_instance_obj.search([('website_url', '=', "%s/" % (website_url))], limit=1)
        if not wc_instance:
            return False
        req_type = ""
        wc_req_type = False
        if url and url.split("/")[0] == "https:":
            url = "%s?consumer_key=%s&consumer_secret=%s" % (
                url, params.get('consumer_key'), params.get('consumer_secret'))
        if url and url.__contains__("wc/v1") or url.__contains__("wc/v2"):
            if url.__contains__("wc/v1"):
                req_type = url.split("?")[0].split("/v1/")[1].replace("/", " ")
            if url.__contains__("wc/v2"):
                req_type = url.split("?")[0].split("/v2/")[1].replace("/", " ")
            result = ''.join(i for i in req_type if not i.isdigit())
            if not result[-1].isalpha():
                result = result[:-1]
            wc_req_type = wc_req_type_obj.search([('name', '=', result.title())], limit=1)
            if not wc_req_type:
                wc_req_type = wc_req_type_obj.create({'name': result.title()})
        if url and url.__contains__("wc-api/v3"):
            req_type = url.split("?")[0].split("/wc-api/v3/")[1].replace("/", " ")
            result = ''.join(i for i in req_type if not i.isdigit())
            if not result[-1].isalpha():
                result = result[:-1]
            wc_req_type = wc_req_type_obj.search([('name', '=', result.title())], limit=1)
            if not wc_req_type:
                wc_req_type = wc_req_type_obj.create({'name': result.title()})
        if self._context.get('tz'):
            tz = pytz.timezone(self._context.get('tz'))
            req_time = pytz.utc.localize(datetime.strptime(req_time, "%d/%m/%Y %H:%M:%S.%f")).astimezone(
                tz).strftime("%d/%m/%Y %H:%M:%S.%f")
            res_time = pytz.utc.localize(datetime.strptime(res_time, "%d/%m/%Y %H:%M:%S.%f")).astimezone(
                tz).strftime("%d/%m/%Y %H:%M:%S.%f")
        try:
            response = json.dumps(res.json(), indent=4)
        except:
            response = res.content
        vals = {
            'url': url,
            'req': data,
            'type': wc_req_type and wc_req_type.id or '',
            'res': response,
            'wc_instance_id': wc_instance.id,
            'req_time': req_time,
            'res_time': res_time
        }
        self.create(vals)
