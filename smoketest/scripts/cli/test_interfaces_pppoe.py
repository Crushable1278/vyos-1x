#!/usr/bin/env python3
#
# Copyright (C) 2019-2023 VyOS maintainers and contributors
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
import unittest

from psutil import process_iter
from base_vyostest_shim import VyOSUnitTestSHIM

from vyos.configsession import ConfigSessionError
from vyos.util import read_file

config_file = '/etc/ppp/peers/{}'
dhcp6c_config_file = '/run/dhcp6c/dhcp6c.{}.conf'
base_path = ['interfaces', 'pppoe']

def get_config_value(interface, key):
    with open(config_file.format(interface), 'r') as f:
        for line in f:
            if line.startswith(key):
                return list(line.split())
    return []

def get_dhcp6c_config_value(interface, key):
    tmp = read_file(dhcp6c_config_file.format(interface))
    tmp = re.findall(r'\n?{}\s+(.*)'.format(key), tmp)

    out = []
    for item in tmp:
        out.append(item.replace(';',''))
    return out

class PPPoEInterfaceTest(VyOSUnitTestSHIM.TestCase):
    def setUp(self):
        self._interfaces = ['pppoe10', 'pppoe20', 'pppoe30']
        self._source_interface = 'eth0'

    def tearDown(self):
        self.cli_delete(base_path)
        self.cli_commit()

    def test_pppoe_client(self):
        # Check if PPPoE dialer can be configured and runs
        for interface in self._interfaces:
            user = 'VyOS-user-' + interface
            passwd = 'VyOS-passwd-' + interface
            mtu = '1400'

            self.cli_set(base_path + [interface, 'authentication', 'user', user])
            self.cli_set(base_path + [interface, 'authentication', 'password', passwd])
            self.cli_set(base_path + [interface, 'default-route', 'auto'])
            self.cli_set(base_path + [interface, 'mtu', mtu])
            self.cli_set(base_path + [interface, 'no-peer-dns'])

            # check validate() - a source-interface is required
            with self.assertRaises(ConfigSessionError):
                self.cli_commit()
            self.cli_set(base_path + [interface, 'source-interface', self._source_interface])

        # commit changes
        self.cli_commit()

        # verify configuration file(s)
        for interface in self._interfaces:
            user = 'VyOS-user-' + interface
            password = 'VyOS-passwd-' + interface

            tmp = get_config_value(interface, 'mtu')[1]
            self.assertEqual(tmp, mtu)
            tmp = get_config_value(interface, 'mru')[1]
            self.assertEqual(tmp, mtu)
            tmp = get_config_value(interface, 'user')[1].replace('"', '')
            self.assertEqual(tmp, user)
            tmp = get_config_value(interface, 'password')[1].replace('"', '')
            self.assertEqual(tmp, password)
            tmp = get_config_value(interface, 'ifname')[1]
            self.assertEqual(tmp, interface)

            # Check if ppp process is running in the interface in question
            running = False
            for p in process_iter():
                if "pppd" in p.name():
                    if interface in p.cmdline():
                        running = True

            self.assertTrue(running)


    def test_pppoe_clent_disabled_interface(self):
        # Check if PPPoE Client can be disabled
        for interface in self._interfaces:
            self.cli_set(base_path + [interface, 'authentication', 'user', 'vyos'])
            self.cli_set(base_path + [interface, 'authentication', 'password', 'vyos'])
            self.cli_set(base_path + [interface, 'source-interface', self._source_interface])
            self.cli_set(base_path + [interface, 'disable'])

            self.cli_commit()

        # Validate PPPoE client process
        running = False
        for interface in self._interfaces:
            for proc in process_iter():
                if interface in proc.cmdline():
                    running = True

        self.assertFalse(running)


    def test_pppoe_dhcpv6pd(self):
        # Check if PPPoE dialer can be configured with DHCPv6-PD
        address = '1'
        sla_id = '0'
        sla_len = '8'
        for interface in self._interfaces:
            self.cli_set(base_path + [interface, 'authentication', 'user', 'vyos'])
            self.cli_set(base_path + [interface, 'authentication', 'password', 'vyos'])
            self.cli_set(base_path + [interface, 'default-route', 'none'])
            self.cli_set(base_path + [interface, 'no-peer-dns'])
            self.cli_set(base_path + [interface, 'source-interface', self._source_interface])
            self.cli_set(base_path + [interface, 'ipv6', 'address', 'autoconf'])

            # prefix delegation stuff
            dhcpv6_pd_base = base_path + [interface, 'dhcpv6-options', 'pd', '0']
            self.cli_set(dhcpv6_pd_base + ['length', '56'])
            self.cli_set(dhcpv6_pd_base + ['interface', self._source_interface, 'address', address])
            self.cli_set(dhcpv6_pd_base + ['interface', self._source_interface, 'sla-id',  sla_id])

            # commit changes
            self.cli_commit()

            # verify "normal" PPPoE value - 1492 is default MTU
            tmp = get_config_value(interface, 'mtu')[1]
            self.assertEqual(tmp, '1492')
            tmp = get_config_value(interface, 'user')[1].replace('"', '')
            self.assertEqual(tmp, 'vyos')
            tmp = get_config_value(interface, 'password')[1].replace('"', '')
            self.assertEqual(tmp, 'vyos')

            for param in ['+ipv6', 'ipv6cp-use-ipaddr']:
                tmp = get_config_value(interface, param)[0]
                self.assertEqual(tmp, param)

            # verify DHCPv6 prefix delegation
            # will return: ['delegation', '::/56 infinity;']
            tmp = get_dhcp6c_config_value(interface, 'prefix')[1].split()[0] # mind the whitespace
            self.assertEqual(tmp, '::/56')
            tmp = get_dhcp6c_config_value(interface, 'prefix-interface')[0].split()[0]
            self.assertEqual(tmp, self._source_interface)
            tmp = get_dhcp6c_config_value(interface, 'ifid')[0]
            self.assertEqual(tmp, address)
            tmp = get_dhcp6c_config_value(interface, 'sla-id')[0]
            self.assertEqual(tmp, sla_id)
            tmp = get_dhcp6c_config_value(interface, 'sla-len')[0]
            self.assertEqual(tmp, sla_len)

            # Check if ppp process is running in the interface in question
            running = False
            for p in process_iter():
                if "pppd" in p.name():
                    running = True
            self.assertTrue(running)

            # We can not check if wide-dhcpv6 process is running as it is started
            # after the PPP interface gets a link to the ISP - but we can see if
            # it would be started by the scripts
            tmp = read_file(f'/etc/ppp/ipv6-up.d/1000-vyos-pppoe-{interface}')
            tmp = re.findall(f'systemctl restart dhcp6c@{interface}.service', tmp)
            self.assertTrue(tmp)

    def test_pppoe_authentication(self):
        # When username or password is set - so must be the other
        interface = 'pppoe0'
        self.cli_set(base_path + [interface, 'authentication', 'user', 'vyos'])
        self.cli_set(base_path + [interface, 'source-interface', self._source_interface])
        self.cli_set(base_path + [interface, 'ipv6', 'address', 'autoconf'])

        # check validate() - if user is set, so must be the password
        with self.assertRaises(ConfigSessionError):
            self.cli_commit()

        self.cli_set(base_path + [interface, 'authentication', 'password', 'vyos'])
        self.cli_commit()

    def test_pppoe_options(self):
        # Check if PPPoE dialer can be configured with DHCPv6-PD
        for interface in self._interfaces:
            user = f'VyOS-user-{interface}'
            passwd = f'VyOS-passwd-{interface}'
            ac_name = f'AC{interface}'
            service_name = f'SRV{interface}'
            host_uniq = 'cafebeefBABE123456'

            self.cli_set(base_path + [interface, 'authentication', 'user', user])
            self.cli_set(base_path + [interface, 'authentication', 'password', passwd])
            self.cli_set(base_path + [interface, 'source-interface', self._source_interface])

            self.cli_set(base_path + [interface, 'access-concentrator', ac_name])
            self.cli_set(base_path + [interface, 'service-name', service_name])
            self.cli_set(base_path + [interface, 'host-uniq', host_uniq])

        # commit changes
        self.cli_commit()

        for interface in self._interfaces:
            ac_name = f'AC{interface}'
            service_name = f'SRV{interface}'
            host_uniq = 'cafebeefBABE123456'

            tmp = get_config_value(interface, 'rp_pppoe_ac')[1]
            self.assertEqual(tmp, f'"{ac_name}"')
            tmp = get_config_value(interface, 'rp_pppoe_service')[1]
            self.assertEqual(tmp, f'"{service_name}"')
            tmp = get_config_value(interface, 'host-uniq')[1]
            self.assertEqual(tmp, f'"{host_uniq}"')

    def test_pppoe_mtu_mru(self):
        # Check if PPPoE dialer can be configured and runs
        for interface in self._interfaces:
            user = f'VyOS-user-{interface}'
            passwd = f'VyOS-passwd-{interface}'
            mtu = '1400'
            mru = '1300'

            self.cli_set(base_path + [interface, 'authentication', 'user', user])
            self.cli_set(base_path + [interface, 'authentication', 'password', passwd])
            self.cli_set(base_path + [interface, 'mtu', mtu])
            self.cli_set(base_path + [interface, 'mru', '9000'])

            # check validate() - a source-interface is required
            with self.assertRaises(ConfigSessionError):
                self.cli_commit()
            self.cli_set(base_path + [interface, 'source-interface', self._source_interface])

            # check validate() - MRU needs to be less or equal then MTU
            with self.assertRaises(ConfigSessionError):
                self.cli_commit()
            self.cli_set(base_path + [interface, 'mru', mru])

        # commit changes
        self.cli_commit()

        # verify configuration file(s)
        for interface in self._interfaces:
            user = f'VyOS-user-{interface}'
            passwd = f'VyOS-passwd-{interface}'

            tmp = get_config_value(interface, 'mtu')[1]
            self.assertEqual(tmp, mtu)
            tmp = get_config_value(interface, 'mru')[1]
            self.assertEqual(tmp, mru)
            tmp = get_config_value(interface, 'user')[1].replace('"', '')
            self.assertEqual(tmp, user)
            tmp = get_config_value(interface, 'password')[1].replace('"', '')
            self.assertEqual(tmp, passwd)
            tmp = get_config_value(interface, 'ifname')[1]
            self.assertEqual(tmp, interface)

if __name__ == '__main__':
    unittest.main(verbosity=2)
