# Copyright 2014 OpenStack Foundation
# All Rights Reserved.
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

from oslo_log import log

from ec2api.tests.functional import base
from ec2api.tests.functional import config

CONF = config.CONF
LOG = log.getLogger(__name__)


class InstanceWithEBSTest(base.EC2TestCase):
    @classmethod
    @base.safe_setup
    def setUpClass(cls):
        super(InstanceWithEBSTest, cls).setUpClass()
        if not CONF.aws.ebs_image_id:
            raise cls.skipException('aws EBS image does not provided')
        cls.image_id = CONF.aws.ebs_image_id
        cls.zone = CONF.aws.aws_zone

    def test_create_get_delete_ebs_instance(self):
        """Launch EBS-backed instance, check results, and terminate it."""
        data = self.client.run_instances(
            ImageId=self.image_id, InstanceType=CONF.aws.instance_type,
            Placement={'AvailabilityZone': self.zone}, MinCount=1, MaxCount=1)
        self.assertEqual(1, len(data['Instances']))
        instance_id = data['Instances'][0]['InstanceId']
        res_clean = self.addResourceCleanUp(self.client.terminate_instances,
                                            InstanceIds=[instance_id])
        self.get_instance_waiter().wait_available(instance_id,
                                                  final_set=('running'))

        instance = self.get_instance(instance_id)

        self.assertEqual('ebs', instance.get('RootDeviceType'))
        self.assertIsNotNone(instance.get('RootDeviceName'))
        bdms = instance.get('BlockDeviceMappings')
        self.assertIsNotNone(bdms)
        rdn = instance['RootDeviceName']
        bdt = [bdt for bdt in bdms if bdt['DeviceName'] == rdn]
        self.assertEqual(1, len(bdt))
        ebs = bdt[0]['Ebs']
        self.assertIsNotNone(ebs)
        volume_id = ebs.get('VolumeId')
        self.assertIsNotNone(volume_id)
        self.assertEqual('attached', ebs.get('Status'))
        if CONF.aws.run_incompatible_tests:
            self.assertTrue(ebs.get('AttachTime'))
            self.assertTrue(ebs.get('DeleteOnTermination'))

        data = self.client.describe_volumes(VolumeIds=[volume_id])
        self.assertEqual(1, len(data['Volumes']))

        data = self.client.terminate_instances(InstanceIds=[instance_id])
        self.cancelResourceCleanUp(res_clean)
        self.get_instance_waiter().wait_delete(instance_id)

    def test_create_root_volume_snapshot(self):
        """Create snapshot of root volume of EBS-backed instance."""
        data = self.client.run_instances(
            ImageId=self.image_id, InstanceType=CONF.aws.instance_type,
            Placement={'AvailabilityZone': self.zone}, MinCount=1, MaxCount=1)
        self.assertEqual(1, len(data['Instances']))
        instance_id = data['Instances'][0]['InstanceId']
        res_clean = self.addResourceCleanUp(self.client.terminate_instances,
                                            InstanceIds=[instance_id])
        self.get_instance_waiter().wait_available(instance_id,
                                                  final_set=('running'))

        bdt = self.get_instance_bdm(instance_id, None)
        self.assertIsNotNone(bdt)
        volume_id = bdt['Ebs'].get('VolumeId')
        self.assertIsNotNone(volume_id)

        data = self.client.stop_instances(InstanceIds=[instance_id])
        self.get_instance_waiter().wait_available(instance_id,
                                                  final_set=('stopped'))

        data = self.client.describe_volumes(VolumeIds=[volume_id])
        self.assertEqual(1, len(data['Volumes']))

        kwargs = {
            'VolumeId': data['Volumes'][0]['VolumeId'],
            'Description': 'Description'
        }
        data = self.client.create_snapshot(*[], **kwargs)
        snapshot_id = data['SnapshotId']
        res_clean_s = self.addResourceCleanUp(self.client.delete_snapshot,
                                              SnapshotId=snapshot_id)
        self.get_snapshot_waiter().wait_available(snapshot_id,
                                                  final_set=('completed'))

        data = self.client.terminate_instances(InstanceIds=[instance_id])
        self.cancelResourceCleanUp(res_clean)
        self.get_instance_waiter().wait_delete(instance_id)

        data = self.client.delete_snapshot(SnapshotId=snapshot_id)
        self.cancelResourceCleanUp(res_clean_s)
        self.get_snapshot_waiter().wait_delete(snapshot_id)
