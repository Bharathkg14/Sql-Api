import json_logging
from datetime import datetime
from json_logging import util
import socket
from json_logging import (
    JSONLogFormatter,
    JSONLogWebFormatter,
    JSONRequestLogFormatter,
)


def jsonlogwebformatter_format_log_object(self, record, request_util):
    json_log_object = super(JSONLogWebFormatter, self)._format_log_object(record, request_util)

    return json_log_object


def jsonlogformatter_format_log_object(self, record, request_util):
    json_log_object = super(JSONLogFormatter, self)._format_log_object(record, request_util)
    json_log_object.update({
        "message": record.getMessage(),
        "type": "log",
        "loggerName": record.name,
        "threadName": record.threadName,
        "level": record.levelname,
        "fileName": record.module,
        "lineNumber": record.lineno,
    })
    if hasattr(record, 'props'):
        json_log_object.update(record.props)
    if record.exc_info or record.exc_text:
        json_log_object.update(self.get_exc_fields(record))
    return json_log_object


def basejsonformatter_format_log_object(self, record, request_util):
    utcnow = datetime.utcnow()
    base_obj = {
        "writtenTime": util.iso_time_format(utcnow),
        "timeStampLocalNano": util.epoch_nano_second(utcnow),
        "hostName": socket.gethostname(),
    }
    base_obj.update(self.base_object_common)
    return base_obj


def jsonrequestlogformatter_format_log_object(self, record, request_util):
    json_log_object = super(JSONRequestLogFormatter, self)._format_log_object(record, request_util)
    request = record.request_info.request
    request_adapter = request_util.request_adapter
    length = request_adapter.get_content_length(request)
    json_log_object.update({
        "type": "request",
        "correlation-id": request_adapter.get_http_header(request, 'correlation-id', json_logging.EMPTY_VALUE),
        "remoteUser": request_adapter.get_remote_user(request),
        "soeid": request_adapter.get_http_header(request, 'soeid', json_logging.EMPTY_VALUE),
        "request": request_adapter.get_path(request),
        "referer": request_adapter.get_http_header(request, 'referer', json_logging.EMPTY_VALUE),
        "xForwardedFor": request_adapter.get_http_header(request, 'x-forwarded-for', json_logging.EMPTY_VALUE),
        "protocol": request_adapter.get_protocol(request),
        "method": request_adapter.get_method(request),
        "remoteIp": request_adapter.get_remote_ip(request),
        "requestSizeB": util.parse_int(length, -1),
        "remoteHost": request_adapter.get_remote_ip(request),
        "remotePort": request_adapter.get_remote_port(request),
        "requestReceivedAt": record.request_info.request_received_at,
        "responseTimeMs": record.request_info.response_time_ms,
        "responseStatus": record.request_info.response_status,
        "responseSizeB": record.request_info.response_size_b,
        "responseContentType": record.request_info.response_content_type,
        "responseSentAt": record.request_info.response_sent_at
    })
    return json_log_object


def init_json_logger():
    json_logging.JSONLogWebFormatter._format_log_object = jsonlogwebformatter_format_log_object
    json_logging.JSONLogFormatter._format_log_object = jsonlogformatter_format_log_object
    json_logging.BaseJSONFormatter._format_log_object = basejsonformatter_format_log_object
    json_logging.JSONRequestLogFormatter._format_log_object = jsonrequestlogformatter_format_log_object