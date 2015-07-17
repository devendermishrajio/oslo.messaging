#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging

import oslo_messaging._drivers.zmq_driver.broker.zmq_base_proxy as base_proxy
from oslo_messaging._drivers.zmq_driver.broker import zmq_call_proxy
from oslo_messaging._drivers.zmq_driver.broker import zmq_fanout_proxy
from oslo_messaging._drivers.zmq_driver import zmq_async
from oslo_messaging._drivers.zmq_driver import zmq_serializer
from oslo_messaging._i18n import _LI

LOG = logging.getLogger(__name__)


class UniversalProxy(base_proxy.BaseProxy):

    def __init__(self, conf, context):
        super(UniversalProxy, self).__init__(conf, context)
        self.poller = zmq_async.get_poller(
            native_zmq=conf.rpc_zmq_native)
        self.tcp_frontend = zmq_call_proxy.FrontendTcpRouter(
            conf, context, poller=self.poller)
        self.backend_matcher = BackendMatcher(
            conf, context, poller=self.poller)
        call = zmq_serializer.CALL_TYPE
        self.call_backend = self.backend_matcher.backends[call]
        LOG.info(_LI("Starting universal-proxy thread"))

    def run(self):
        message, socket = self.poller.poll(self.conf.rpc_poll_timeout)
        if message is None:
            return

        LOG.info(_LI("Received message at universal proxy: %s") % str(message))

        if socket == self.tcp_frontend.frontend:
            self.backend_matcher.redirect_to_backend(message)
        else:
            self.tcp_frontend.redirect_outgoing_reply(message)


class BackendMatcher(base_proxy.BaseBackendMatcher):

    def __init__(self, conf, context, poller=None):
        super(BackendMatcher, self).__init__(conf, poller, context)
        direct_backend = zmq_call_proxy.DealerBackend(conf, context, poller)
        self.backends[zmq_serializer.CALL_TYPE] = direct_backend
        self.backends[zmq_serializer.CAST_TYPE] = direct_backend
        fanout_backend = zmq_fanout_proxy.PublisherBackend(conf, context)
        self.backends[zmq_serializer.FANOUT_TYPE] = fanout_backend

    def redirect_to_backend(self, message):
        message_type = zmq_serializer.get_msg_type(message)
        self.backends[message_type].redirect_to_backend(message)