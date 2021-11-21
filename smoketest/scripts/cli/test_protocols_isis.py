#!/usr/bin/env python3
#
# Copyright (C) 2021 VyOS maintainers and contributors
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

import unittest

from base_vyostest_shim import VyOSUnitTestSHIM
from vyos.configsession import ConfigSessionError
from vyos.ifconfig import Section
from vyos.util import process_named_running

PROCESS_NAME = 'isisd'
base_path = ['protocols', 'isis']

domain = 'VyOS'
net = '49.0001.1921.6800.1002.00'

class TestProtocolsISIS(VyOSUnitTestSHIM.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._interfaces = Section.interfaces('ethernet')

        # call base-classes classmethod
        super(cls, cls).setUpClass()

    def tearDown(self):
        self.cli_delete(base_path)
        self.cli_commit()

        # Check for running process
        self.assertTrue(process_named_running(PROCESS_NAME))

    def isis_base_config(self):
        self.cli_set(base_path + ['net', net])
        for interface in self._interfaces:
            self.cli_set(base_path + ['interface', interface])

    def test_isis_01_redistribute(self):
        prefix_list = 'EXPORT-ISIS'
        route_map = 'EXPORT-ISIS'
        rule = '10'

        self.cli_set(['policy', 'prefix-list', prefix_list, 'rule', rule, 'action', 'permit'])
        self.cli_set(['policy', 'prefix-list', prefix_list, 'rule', rule, 'prefix', '203.0.113.0/24'])
        self.cli_set(['policy', 'route-map', route_map, 'rule', rule, 'action', 'permit'])
        self.cli_set(['policy', 'route-map', route_map, 'rule', rule, 'match', 'ip', 'address', 'prefix-list', prefix_list])

        self.cli_set(base_path)

        # verify() - net id and interface are mandatory
        with self.assertRaises(ConfigSessionError):
            self.cli_commit()

        self.isis_base_config()
        self.cli_set(base_path + ['redistribute', 'ipv4', 'connected', 'level-2', 'route-map', route_map])
        self.cli_set(base_path + ['log-adjacency-changes'])

        # Commit all changes
        self.cli_commit()

        # Verify all changes
        tmp = self.getFRRconfig(f'router isis {domain}')
        self.assertIn(f' net {net}', tmp)
        self.assertIn(f' log-adjacency-changes', tmp)
        self.assertIn(f' redistribute ipv4 connected level-2 route-map {route_map}', tmp)

        for interface in self._interfaces:
            tmp = self.getFRRconfig(f'interface {interface}')
            self.assertIn(f' ip router isis {domain}', tmp)
            self.assertIn(f' ipv6 router isis {domain}', tmp)

        self.cli_delete(['policy', 'route-map', route_map])
        self.cli_delete(['policy', 'prefix-list', prefix_list])

    def test_isis_02_zebra_route_map(self):
        # Implemented because of T3328
        route_map = 'foo-isis-in'

        self.cli_set(['policy', 'route-map', route_map, 'rule', '10', 'action', 'permit'])

        self.isis_base_config()
        self.cli_set(base_path + ['redistribute', 'ipv4', 'connected', 'level-2', 'route-map', route_map])
        self.cli_set(base_path + ['route-map', route_map])

        # commit changes
        self.cli_commit()

        # Verify FRR configuration
        zebra_route_map = f'ip protocol isis route-map {route_map}'
        frrconfig = self.getFRRconfig(zebra_route_map)
        self.assertIn(zebra_route_map, frrconfig)

        # Remove the route-map again
        self.cli_delete(base_path + ['route-map'])
        # commit changes
        self.cli_commit()

        # Verify FRR configuration
        frrconfig = self.getFRRconfig(zebra_route_map)
        self.assertNotIn(zebra_route_map, frrconfig)

        self.cli_delete(['policy', 'route-map', route_map])

    def test_isis_03_default_information(self):
        metric = '50'
        route_map = 'default-foo-'

        self.isis_base_config()
        for afi in ['ipv4', 'ipv6']:
            for level in ['level-1', 'level-2']:
                self.cli_set(base_path + ['default-information', 'originate', afi, level, 'always'])
                self.cli_set(base_path + ['default-information', 'originate', afi, level, 'metric', metric])
                self.cli_set(base_path + ['default-information', 'originate', afi, level, 'route-map', route_map + level + afi])

        # Commit all changes
        self.cli_commit()

        # Verify all changes
        tmp = self.getFRRconfig(f'router isis {domain}')
        self.assertIn(f' net {net}', tmp)

        for afi in ['ipv4', 'ipv6']:
            for level in ['level-1', 'level-2']:
                route_map_name = route_map + level + afi
                self.assertIn(f' default-information originate {afi} {level} always route-map {route_map_name} metric {metric}', tmp)

    def test_isis_04_password(self):
        password = 'foo'

        self.isis_base_config()

        self.cli_set(base_path + ['area-password', 'plaintext-password', password])
        self.cli_set(base_path + ['area-password', 'md5', password])
        self.cli_set(base_path + ['domain-password', 'plaintext-password', password])
        self.cli_set(base_path + ['domain-password', 'md5', password])

        # verify() - can not use both md5 and plaintext-password for area-password
        with self.assertRaises(ConfigSessionError):
            self.cli_commit()
        self.cli_delete(base_path + ['area-password', 'md5', password])

        # verify() - can not use both md5 and plaintext-password for domain-password
        with self.assertRaises(ConfigSessionError):
            self.cli_commit()
        self.cli_delete(base_path + ['domain-password', 'md5', password])

        # Commit all changes
        self.cli_commit()

        # Verify all changes
        tmp = self.getFRRconfig(f'router isis {domain}')
        self.assertIn(f' net {net}', tmp)
        self.assertIn(f' domain-password clear {password}', tmp)
        self.assertIn(f' area-password clear {password}', tmp)

if __name__ == '__main__':
    unittest.main(verbosity=2)
