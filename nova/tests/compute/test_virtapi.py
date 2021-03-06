# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright 2012 IBM Corp.
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

import mox

from nova.compute import manager as compute_manager
from nova import context
from nova import db
from nova import test
from nova.virt import fake
from nova.virt import virtapi


class VirtAPIBaseTest(test.TestCase):
    def setUp(self):
        super(VirtAPIBaseTest, self).setUp()
        self.context = context.RequestContext('fake-user', 'fake-project')

    @classmethod
    def set_up_virtapi(cls):
        cls.virtapi = virtapi.VirtAPI()

    @classmethod
    def setUpClass(cls):
        super(VirtAPIBaseTest, cls).setUpClass()
        cls.set_up_virtapi()
        cls._totest_methods = [x for x in dir(cls.virtapi)
                               if not x.startswith('_')]
        cls._tested_methods = [x for x in dir(cls)
                               if x.startswith('test_')]

    def _tested_method(self, method):
        self._tested_methods.remove('test_' + method)
        self._totest_methods.remove(method)

    def run(self, result):
        super(VirtAPIBaseTest, self).run(result)
        if not self._tested_methods:
            self.assertEqual(self._totest_methods, [])

    def assertExpected(self, method, *args, **kwargs):
        self.assertRaises(NotImplementedError,
                          getattr(self.virtapi, method), self.context,
                          *args, **kwargs)
        self._tested_method(method)

    def test_instance_update(self):
        self.assertExpected('instance_update', 'fake-uuid',
                            dict(host='foohost'))

    def test_instance_get_by_uuid(self):
        self.assertExpected('instance_get_by_uuid', 'fake-uuid')

    def test_instance_get_all_by_host(self):
        self.assertExpected('instance_get_all_by_host', 'fake-host')

    def test_aggregate_get_by_host(self):
        self.assertExpected('aggregate_get_by_host', 'fake-host', key=None)

    def test_aggregate_metadata_add(self):
        self.assertExpected('aggregate_metadata_add', {'id': 'fake'},
                            {'foo': 'bar'}, set_delete=False)

    def test_aggregate_metadata_delete(self):
        self.assertExpected('aggregate_metadata_delete', {'id': 'fake'},
                            'foo')

    def test_security_group_get_by_instance(self):
        self.assertExpected('security_group_get_by_instance', 'fake-uuid')

    def test_security_group_rule_get_by_security_group(self):
        self.assertExpected('security_group_rule_get_by_security_group',
                            'fake-id')

    def test_provider_fw_rule_get_all(self):
        self.assertExpected('provider_fw_rule_get_all')

    def test_agent_build_get_by_triple(self):
        self.assertExpected('agent_build_get_by_triple',
                            'fake-hv', 'gnu/hurd', 'fake-arch')


class FakeVirtAPITest(VirtAPIBaseTest):
    @classmethod
    def set_up_virtapi(cls):
        cls.virtapi = fake.FakeVirtAPI()

    def assertExpected(self, method, *args, **kwargs):
        if method == 'instance_update':
            # NOTE(danms): instance_update actually becomes the other variant
            # in FakeVirtAPI
            db_method = 'instance_update_and_get_original'
        else:
            db_method = method
        self.mox.StubOutWithMock(db, db_method)

        if method in ('aggregate_metadata_add', 'aggregate_metadata_delete'):
            # NOTE(danms): FakeVirtAPI will convert the aggregate to
            # aggregate['id'], so expect that in the actual db call
            e_args = tuple([args[0]['id']] + list(args[1:]))
        else:
            e_args = args

        getattr(db, db_method)(self.context, *e_args, **kwargs).AndReturn(
            'it worked')
        self.mox.ReplayAll()
        result = getattr(self.virtapi, method)(self.context, *args, **kwargs)
        self.assertEqual(result, 'it worked')
        self._tested_method(method)


class FakeCompute(object):
    def __init__(self):
        self.conductor_api = mox.MockAnything()
        self.db = mox.MockAnything()

    def _instance_update(self, context, instance_uuid, **kwargs):
        # NOTE(danms): Fake this behavior from compute/manager::ComputeManager
        return self.conductor_api.instance_update(context,
                                                  instance_uuid, kwargs)


class ComputeVirtAPITest(VirtAPIBaseTest):
    @classmethod
    def set_up_virtapi(cls):
        cls.compute = FakeCompute()
        cls.virtapi = compute_manager.ComputeVirtAPI(cls.compute)

    @classmethod
    def setUpClass(cls):
        super(ComputeVirtAPITest, cls).setUpClass()
        # NOTE(danms): Eventually these should all be migrated to the
        # conductor, but until then, dispatch appropriately.
        cls.conductor_methods = ['instance_update', 'instance_get_by_uuid',
                                 'instance_get_all_by_host',
                                 'aggregate_get_by_host',
                                 'aggregate_metadata_add',
                                 'aggregate_metadata_delete',
                                  ]
        cls.db_methods = ['security_group_get_by_instance',
                          'security_group_rule_get_by_security_group',
                          'provider_fw_rule_get_all',
                          'agent_build_get_by_triple',
                           ]

    def assertExpected(self, method, *args, **kwargs):
        if method in self.conductor_methods:
            target = self.compute.conductor_api
        elif method in self.db_methods:
            target = self.compute.db
        else:
            raise Exception('Method "%s" not known to this test!')

        self.mox.StubOutWithMock(target, method)
        getattr(target, method)(self.context, *args, **kwargs).AndReturn(
            'it worked')
        self.mox.ReplayAll()
        result = getattr(self.virtapi, method)(self.context, *args, **kwargs)
        self.assertEqual(result, 'it worked')
        self._tested_method(method)
