"""GitHub: repo audit activity and account entitlement history.

GitHub repo activity is contextual; don't infer all permissions were exercised.
"""
from .common import COMMON_NUMERIC
CONFIG = {
    'categorical': ('account_type', 'permission_profile', 'department'),
    'numeric': COMMON_NUMERIC + (
        'github_repo_activity_events', 'github_repo_activity_coverage_known',
        'ad_group_data_known', 'unmapped_ad_group_count',
    ),
    'signal_event': 'github_repo_activity',
    'signal_count': 'github_repo_activity_events',
    'signal_known': 'github_repo_activity_coverage_known',
}
