# -*- coding: utf-8 -*-
import re
from traceback import format_exc

import pytest
from wrapanapi.utils import eval_strings

from cfme.containers.provider import ContainersProvider
from cfme.intelligence.reports.reports import CannedSavedReport, CustomReport
from utils import testgen
from utils.blockers import BZ
from utils.appliance.implementations.ui import navigate_to


pytestmark = [
    pytest.mark.usefixtures('setup_provider'),
    pytest.mark.meta(blockers=[BZ(1467059, forced_streams=["5.8"])]),
    pytest.mark.meta(
        server_roles='+ems_metrics_coordinator +ems_metrics_collector +ems_metrics_processor'),
    pytest.mark.tier(1)]
pytest_generate_tests = testgen.generate([ContainersProvider], scope='function')


@pytest.fixture(scope='module')
def node_hardwares_db_data(appliance):

    """Grabbing hardwares table data for nodes"""

    db = appliance.db.client
    hardwares_table = db['hardwares']
    container_nodes = db['container_nodes']

    out = {}
    for node in db.session.query(container_nodes).all():

        out[node.name] = hardwares_table.__table__.select().where(
            hardwares_table.id == node.id
        ).execute().fetchone()

    return out


def get_vpor_data_by_name(vporizer_, name):
    return [vals for vals in vporizer_ if vals.resource_name == name]


def get_report(menu_name, candu=False):
    """Queue a report by menu name , wait for finish and return it"""
    path_to_report = ['Configuration Management', 'Containers', menu_name]
    try:
        run_at = CannedSavedReport.queue_canned_report(path_to_report)
    except CandidateNotFound:
        pytest.skip('Could not find report "{}" in containers.\nTraceback:\n{}'
                    .format(path_to_report, format_exc()))
    return CannedSavedReport(path_to_report, run_at, candu=candu)


@pytest.mark.polarion('CMP-10617')
def test_container_reports_base_on_options(soft_assert):
    """This test verifies that all containers options are available in the report 'based on'
    Dropdown in the report creation"""
    navigate_to(CustomReport, 'New')
    for base_on in (
        'Chargeback Container Images',
        'Container Images',
        'Container Services',
        'Container Templates',
        'Containers',
        re.compile('Performance - Container\s*Nodes'),
        re.compile('Performance - Container\s*Projects'),
        'Performance - Containers'
    ):
        compare = (base_on.match if hasattr(base_on, 'match') else base_on.__eq__)
        option = [opt for opt in select(id="chosen_model").all_options
                  if compare(str(opt.text))]
        soft_assert(option, 'Could not find option "{}" for base report on.'.format(base_on))


@pytest.mark.polarion('CMP-9533')
def test_report_pods_per_ready_status(soft_assert, provider):
    """Testing 'Pods per Ready Status' report, see polarion case for more info"""
    pods_per_ready_status = provider.pods_per_ready_status()
    report = get_report('Pods per Ready Status')
    for row in report.data.rows:
        name = row['# Pods per Ready Status']
        readiness_ui = eval_strings([row['Ready Condition Status']]).pop()
        if soft_assert(name in pods_per_ready_status,  # this check based on BZ#1435958
                'Could not find pod "{}" in openshift.'
                .format(name)):
            expected_readiness = pods_per_ready_status.get(name, {}).get('Ready', False)
            soft_assert(expected_readiness == readiness_ui,
                        'For pod "{}" expected readiness is "{}" Found "{}"'
                        .format(name, expected_readiness, readiness_ui))


@pytest.mark.polarion('CMP-9536')
def test_report_nodes_by_capacity(appliance, soft_assert, node_hardwares_db_data):
    """Testing 'Nodes By Capacity' report, see polarion case for more info"""
    report = get_report('Nodes By Capacity')
    for row in report.data.rows:

        hw = node_hardwares_db_data[row['Name']]

        soft_assert(hw.cpu_total_cores == int(row['CPU Cores']),
                    'Number of CPU cores is wrong: expected {}'
                    ' got {}'.format(hw.cpu_total_cores, row['CPU Cores']))

        # The following block is to convert whatever we have to MB
        memory_ui = float(re.sub(r'[a-zA-Z,]', '', row['Memory']))
        if 'gb' in row['Memory'].lower():
            memory_mb_ui = memory_ui * 1024
            # Shift hw.memory_mb to GB, round to the number of decimals of memory_mb_db
            # and shift back to MB:
            memory_mb_db = round(hw.memory_mb / 1024.0,
                                 len(str(memory_mb_ui).split('.')[1])) * 1024
        else:  # Assume it's MB
            memory_mb_ui = memory_ui
            memory_mb_db = hw.memory_mb

        soft_assert(memory_mb_ui == memory_mb_db,
                    'Memory (MB) is wrong for node "{}": expected {} got {}'
                    .format(row['Name'], memory_mb_ui, memory_mb_db))


@pytest.mark.polarion('CMP-10033')
def test_report_nodes_by_cpu_usage(appliance, soft_assert, vporizer):
    """Testing 'Nodes By CPU Usage' report, see polarion case for more info"""
    report = get_report('Nodes By CPU Usage')
    for row in report.data.rows:

        vpor_values = get_vpor_data_by_name(vporizer, row["Name"])[0]
        usage_db = round(vpor_values.max_cpu_usage_rate_average, 2)
        usage_report = round(float(row['CPU Usage (%)']), 2)

        soft_assert(usage_db == usage_report,
                    'CPU usage is wrong for node "{}": expected {} got {}'
                    .format(row['Name'], usage_db, usage_report))


@pytest.mark.polarion('CMP-10034')
def test_report_nodes_by_memory_usage(appliance, soft_assert, vporizer):
    """Testing 'Nodes By Memory Usage' report, see polarion case for more info"""
    report = get_report('Nodes By Memory Usage')
    for row in report.data.rows:

        vpor_values = get_vpor_data_by_name(vporizer, row["Name"])[0]
        usage_db = round(vpor_values.max_mem_usage_absolute_average, 2)
        usage_report = round(float(row['Memory Usage (%)']), 2)

        soft_assert(usage_db == usage_report,
                    'CPU usage is wrong for node "{}": expected {} got {}.'
                    .format(row['Name'], usage_db, usage_report))


@pytest.mark.polarion('CMP-10669')
def test_report_number_of_nodes_per_cpu_cores(soft_assert, node_hardwares_db_data):
    """Testing 'Number of Nodes per CPU Cores' report, see polarion case for more info"""
    report = get_report('Nodes by Number of CPU Cores')
    for row in report.data.rows:

        hw = node_hardwares_db_data[row['Name']]

        soft_assert(hw.cpu_total_cores == int(row['Hardware Number of CPU Cores']),
                    'Hardware Number of CPU Cores is wrong for node "{}": expected {} got {}.'
                    .format(row['Name'], hw.cpu_total_cores, row['Hardware Number of CPU Cores']))


@pytest.mark.polarion('CMP-10008')
def test_report_projects_by_number_of_pods(appliance, soft_assert):

    """Testing 'Projects by Number of Pods' report, see polarion case for more info"""

    container_projects = appliance.db.client['container_projects']
    container_pods = appliance.db.client['container_groups']

    report = get_report('Projects by Number of Pods')
    for row in report.data.rows:
        pods_count = len(container_pods.__table__.select().where(
            container_pods.container_project_id ==
            container_projects.__table__.select().where(
                container_projects.name == row['Project Name']).execute().fetchone().id
        ).execute().fetchall())

        soft_assert(pods_count == int(row['Number of Pods']),
                    'Number of pods is wrong for project "{}". expected {} got {}.'
                    .format(row['Project Name'], pods_count, row['Number of Pods']))


@pytest.mark.polarion('CMP-10009')
def test_report_projects_by_cpu_usage(soft_assert, vporizer):
    """Testing 'Projects By CPU Usage' report, see polarion case for more info"""
    report = get_report('Projects By CPU Usage')
    for row in report.data.rows:

        vpor_values = get_vpor_data_by_name(vporizer, row["Name"])[0]
        usage_db = round(vpor_values.max_cpu_usage_rate_average, 2)
        usage_report = round(float(row['CPU Usage (%)']), 2)

        soft_assert(usage_db == usage_report,
                    'CPU usage is wrong for project "{}": expected {} got {}'
                    .format(row['Name'], usage_db, usage_report))


@pytest.mark.polarion('CMP-10010')
def test_report_projects_by_memory_usage(soft_assert, vporizer):
    """Testing 'Projects By Memory Usage' report, see polarion case for more info"""
    report = get_report('Projects By Memory Usage')
    for row in report.data.rows:

        vpor_values = get_vpor_data_by_name(vporizer, row["Name"])[0]
        usage_db = round(vpor_values.max_mem_usage_absolute_average, 2)
        usage_report = round(float(row['Memory Usage (%)']), 2)

        soft_assert(usage_db == usage_report,
                    'CPU usage is wrong for project "{}": expected {} got {}.'
                    .format(row['Name'], usage_db, usage_report))


@pytest.mark.long_running_env
@pytest.mark.polarion('CMP-10272')
def test_report_pod_counts_for_container_images_by_project(provider, soft_assert):
    """Testing 'Pod counts For Container Images by Project' report,\
    see polarion case for more info"""
    report = get_report('Pod counts For Container Images by Project', candu=True)

    for project_entities in report.data:
        if not project_entities.id.startswith('Name:'):
            # Columns like: All Rows | Count: x
            continue
        id_match = re.search(r'Name: (.+) \|', project_entities.id)
        if id_match:
            project_name = id_match.group(1)
        else:
            raise Exception('Could not parse project name from summary row: {}'
                            .format(project_entities.id))

        # TODO: Add this logic to wrapanapi:
        pods_api = [pd for pd in provider.mgmt.api.get('pod')[1]['items']
                    if pd['metadata']['namespace'] == project_name]
        # Collecting images per pod from the report
        images_per_pod = {}
        for row in project_entities.rows:
            pod_name = row['Pod Name']
            if pod_name not in images_per_pod:
                images_per_pod[pod_name] = []
            images_per_pod[pod_name].append(row['Image Name'])
        # Going over each pod from the API and checking that it founds in the report
        # under the current project and that its image founds in the pod's images.
        for pd in pods_api:
            expected_pod = pd['metadata']['name']
            expected_image = pd['spec']['containers'][-1]['image']
            if not soft_assert(expected_pod in images_per_pod,
                               'Couldn\'t find pod {} in report'.format(expected_pod)):
                continue
            pod_images = images_per_pod[expected_pod]
            # Use 'in' since the image name in the API may include also registry and tag
            is_image = filter(lambda img_nm: img_nm in expected_image, pod_images)
            soft_assert(is_image,
                        'Could not find image "{}" in pod "{}". Pod images in report: {}'
                        .format(expected_image, expected_pod, pod_images))


@pytest.mark.long_running_env
@pytest.mark.polarion('CMP-9532')
def test_report_recently_discovered_pods(provider, soft_assert):
    """Testing 'Recently Discovered Pods' report, see polarion case for more info"""
    report = get_report('Recently Discovered Pods')
    pods_in_report = [row['Name'] for row in report.data.rows]
    pods_per_ready_status = provider.pods_per_ready_status()
    for pod in pods_per_ready_status.keys():

        soft_assert(pod in pods_in_report,
                    'Could not find pod "{}" in report.'.format(pod))


@pytest.mark.long_running_env
@pytest.mark.polarion('CMP-10273')
def test_report_number_of_images_per_node(provider, soft_assert):
    """Testing 'Number of Images per Node' report, see polarion case for more info"""
    pods_api = provider.mgmt.api.get('pod')[-1]['items']
    report = get_report('Number of Images per Node', candu=True)
    report_data = {node_data.id.split(' |')[0]: node_data.rows for node_data in report.data}
    for pod in pods_api:
        expected_image = pod['spec']['containers'][0]['image']
        node = pod['spec']['nodeName']
        report_node_data = report_data[node]
        pod_name = pod['metadata']['name']
        pod_images = [row['Image Name'] for row in report_node_data
                      if row['Pod Name'] == pod_name]
        # Use 'in' since the image name in the API may include also registry and tag
        is_image = filter(lambda img_nm: img_nm in expected_image, pod_images)
        soft_assert(is_image,
                    'Expected image for pod "{0}" in node {1} is "{2}". found images: {3}'
                    .format(pod_name, node, expected_image, pod_images))


@pytest.mark.long_running_env
@pytest.mark.polarion('CMP-10670')
def test_report_projects_by_number_of_containers(provider, soft_assert):
    """Testing 'Projects by Number of Containers' report, see polarion case for more info"""
    report = get_report('Projects by Number of Containers')
    pods_api = provider.mgmt.api.get('pod')[-1]['items']

    # Since there is no provider column, in case of more than 1 provider we get some projects
    # multiple times in the report. Because of that for each project name we are collecting
    # all the 'Containers Count' columns and then checking that the containers count that we
    # fetched from the API is found _in_ the counts under this project name
    projects_containers_count = {}
    for row in report.data.rows:
        if row['Project Name'] not in projects_containers_count:
            projects_containers_count[row['Project Name']] = []
        projects_containers_count[row['Project Name']].append(int(row['Containers Count']))

    for project_name, containers_counts in projects_containers_count.items():
        containers_counts_api = sum(
            [len(pod['spec']['containers']) for pod in pods_api
            if pod['metadata']['namespace'] == project_name]
        )
        soft_assert(containers_counts_api in containers_counts,
                    'Expected containers count for project {} should be {}. Found {} instead.'
                    .format(project_name, containers_counts_api, containers_counts_api))
