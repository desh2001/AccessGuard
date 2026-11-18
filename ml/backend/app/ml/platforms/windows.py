"""Windows/AD: access lifecycle, groups and privileged logon context.

A 4672 special-privileges-assigned event is not proof of misconduct.
"""
from .common import COMMON_NUMERIC
CONFIG = {
    'categorical': ('account_type', 'permission_profile', 'department'),
    'numeric': COMMON_NUMERIC + (
        'ad_group_count', 'privileged_ad_group_count', 'ad_group_data_known',
        'mapped_access_ad_group_count', 'unmapped_ad_group_count',
        'group_catalog_coverage_fraction', 'manager_changes_window',
        'department_changes_window', 'ad_department_mismatch',
        'windows_privileged_logon_events', 'windows_privileged_logon_coverage_known',
    ),
    'signal_event': 'windows_privileged_logon',
    'signal_count': 'windows_privileged_logon_events',
    'signal_known': 'windows_privileged_logon_coverage_known',
}
