#!/usr/bin/env python3
#
# Copyright (C) 2019-2020 VyOS maintainers and contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or later as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
import os
import unittest

from base_vyostest_shim import VyOSUnitTestSHIM

from vyos.configsession import ConfigSessionError
from vyos.util import cmd
from vyos.util import process_running

PROCESS_NAME = 'ddclient'
DDCLIENT_CONF = '/run/ddclient/ddclient.conf'
DDCLIENT_PID = '/run/ddclient/ddclient.pid'
base_path = ['service', 'dns', 'dynamic']

def get_config_value(key):
    tmp = cmd(f'sudo cat {DDCLIENT_CONF}')
    tmp = re.findall(r'\n?{}=+(.*)'.format(key), tmp)
    tmp = tmp[0].rstrip(',')
    return tmp

class TestServiceDDNS(VyOSUnitTestSHIM.TestCase):

    def tearDown(self):
        # Delete DDNS configuration
        self.cli_delete(base_path)
        self.cli_commit()

    def test_dyndns_service(self):
        ddns = ['interface', 'eth0', 'service']
        services = ['cloudflare', 'afraid', 'dyndns', 'zoneedit']

        for service in services:
            user = 'vyos_user'
            password = 'vyos_pass'
            zone = 'vyos.io'
            self.cli_delete(base_path)
            self.cli_set(base_path + ddns + [service, 'host-name', 'test.ddns.vyos.io'])
            self.cli_set(base_path + ddns + [service, 'login', user])
            self.cli_set(base_path + ddns + [service, 'password', password])
            self.cli_set(base_path + ddns + [service, 'zone', zone])

            # commit changes
            if service == 'cloudflare':
                self.cli_commit()
            else:
                # zone option only works on cloudflare, an exception is raised
                # for all others
                with self.assertRaises(ConfigSessionError):
                    self.cli_commit()
                self.cli_delete(base_path + ddns + [service, 'zone', 'vyos.io'])
                # commit changes again - now it should work
                self.cli_commit()

            # we can only read the configuration file when we operate as 'root'
            protocol = get_config_value('protocol')
            login = get_config_value('login')
            pwd = get_config_value('password')

            # some services need special treatment
            protoname = service
            if service == 'cloudflare':
                tmp = get_config_value('zone')
                self.assertTrue(tmp == zone)
            elif service == 'afraid':
                protoname = 'freedns'
            elif service == 'dyndns':
                protoname = 'dyndns2'
            elif service == 'zoneedit':
                protoname = 'zoneedit1'

            self.assertTrue(protocol == protoname)
            self.assertTrue(login == user)
            self.assertTrue(pwd == "'" + password + "'")

            # Check for running process
            self.assertTrue(process_running(DDCLIENT_PID))

    def test_dyndns_rfc2136(self):
        # Check if DDNS service can be configured and runs
        ddns = ['interface', 'eth0', 'rfc2136', 'vyos']
        ddns_key_file = '/config/auth/my.key'

        self.cli_set(base_path + ddns + ['key', ddns_key_file])
        self.cli_set(base_path + ddns + ['record', 'test.ddns.vyos.io'])
        self.cli_set(base_path + ddns + ['server', 'ns1.vyos.io'])
        self.cli_set(base_path + ddns + ['ttl', '300'])
        self.cli_set(base_path + ddns + ['zone', 'vyos.io'])

        # ensure an exception will be raised as no key is present
        if os.path.exists(ddns_key_file):
            os.unlink(ddns_key_file)

        # check validate() - the key file does not exist yet
        with self.assertRaises(ConfigSessionError):
            self.cli_commit()

        with open(ddns_key_file, 'w') as f:
            f.write('S3cretKey')

        # commit changes
        self.cli_commit()

        # TODO: inspect generated configuration file

        # Check for running process
        self.assertTrue(process_running(DDCLIENT_PID))

if __name__ == '__main__':
    unittest.main(verbosity=2)
