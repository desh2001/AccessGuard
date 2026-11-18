"""Linux: access lifecycle, permission history and audited sudo context.

Sudo use alone is not an authorization violation; policy is separate.
"""
from .common import COMMON_NUMERIC
CONFIG = {
    'categorical': ('account_type', 'permission_profile', 'department'),
    'numeric': COMMON_NUMERIC + (
        'ad_group_data_known', 'privileged_ad_group_count',
        'linux_sudo_events', 'linux_sudo_coverage_known',
    ),
    'signal_event': 'linux_sudo',
    'signal_count': 'linux_sudo_events',
    'signal_known': 'linux_sudo_coverage_known',
}
