"""Quarterly ML V10: coverage, AD groups, transfers, policies, quarantine,
quarterly review cycles, review outcomes, CSV import and ML training provenance.

Additive only — existing rows remain compatible.

Revision ID: 0003_quarterly_ml_v10
Revises: 0002_research_lab
"""
from alembic import op
import sqlalchemy as sa

revision = '0003_quarterly_ml_v10'
down_revision = '0002_research_lab'
branch_labels = None
depends_on = None


def upgrade():
    # ── Extend existing tables ────────────────────────────────────────────
    # System: controlled platform mapping
    op.add_column('systems', sa.Column('platform', sa.String(30), nullable=True))

    # Account: stable native identifiers
    op.add_column('accounts', sa.Column('native_id', sa.String(255), nullable=True))
    op.add_column('accounts', sa.Column('native_id_type', sa.String(40), nullable=True))

    # AccessGrant: sensitivity tier
    op.add_column('access_grants', sa.Column('sensitivity', sa.String(30), nullable=True))

    # ActivityEvent: provenance additions
    op.add_column('activity_events', sa.Column('source_event_id', sa.String(255), nullable=True))
    op.add_column('activity_events', sa.Column('event_type', sa.String(80), nullable=True))
    op.add_column('activity_events', sa.Column('device_id', sa.String(255), nullable=True))
    op.add_column('activity_events', sa.Column('resource_key', sa.String(255), nullable=True))
    op.add_column('activity_events', sa.Column('received_at', sa.DateTime(timezone=True), nullable=True))
    # Dedup constraint — only where source_event_id is not null (partial unique)
    op.create_index('ix_activity_event_type_occurred', 'activity_events', ['event_type', 'occurred_at'])

    # ── New tables ────────────────────────────────────────────────────────
    op.create_table('activity_coverage',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('platform', sa.String(30), nullable=False),
        sa.Column('source', sa.String(60), nullable=False),
        sa.Column('event_type', sa.String(80), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=True),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_complete', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attested_by', sa.String(120), nullable=False),
        sa.Column('attested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('record_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('connector_run_id', sa.Integer(), sa.ForeignKey('connector_runs.id'), nullable=True),
        sa.CheckConstraint('is_complete IN (0, 1)', name='coverage_complete_flag'),
    )
    op.create_index('ix_coverage_platform_dates', 'activity_coverage', ['platform', 'start_at', 'end_at'])

    op.create_table('ad_group_catalog',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('org_id', sa.String(60), nullable=False, server_default='default'),
        sa.Column('directory_id', sa.String(120), nullable=False),
        sa.Column('group_key', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('access_relevance', sa.String(30), nullable=False, server_default='unknown'),
        sa.Column('privilege_tier', sa.String(30), nullable=True),
        sa.Column('allowed_departments', sa.Text(), nullable=True),
        sa.Column('allowed_roles', sa.Text(), nullable=True),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('owner', sa.String(120), nullable=True),
        sa.Column('approver', sa.String(120), nullable=True),
        sa.Column('updated_by', sa.String(120), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('org_id', 'directory_id', 'group_key', name='uq_ad_group_catalog'),
        sa.CheckConstraint("access_relevance IN ('access','non_access','unknown')", name='ad_group_relevance_valid'),
    )

    op.create_table('ad_group_membership_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('identity_id', sa.String(32), sa.ForeignKey('identities.id'), nullable=False),
        sa.Column('org_id', sa.String(60), nullable=False, server_default='default'),
        sa.Column('directory_id', sa.String(120), nullable=False),
        sa.Column('group_key', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(60), nullable=True),
    )
    op.create_index('ix_ad_membership_identity', 'ad_group_membership_history', ['identity_id'])

    op.create_table('employee_transfers',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('identity_id', sa.String(32), sa.ForeignKey('identities.id'), nullable=False),
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('from_department', sa.String(100), nullable=True),
        sa.Column('to_department', sa.String(100), nullable=True),
        sa.Column('from_manager', sa.String(120), nullable=True),
        sa.Column('to_manager', sa.String(120), nullable=True),
        sa.Column('from_org_unit', sa.String(120), nullable=True),
        sa.Column('to_org_unit', sa.String(120), nullable=True),
        sa.Column('source_reference', sa.String(255), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('reviewer_disposition', sa.String(80), nullable=True),
        sa.CheckConstraint("status IN ('pending','acknowledged','reviewed','dismissed')", name='transfer_status_valid'),
    )
    op.create_index('ix_transfers_identity', 'employee_transfers', ['identity_id'])

    op.create_table('managed_resource_policies',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('resource_key', sa.String(255), nullable=False, unique=True),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('business_owner', sa.String(120), nullable=True),
        sa.Column('permitted_departments', sa.Text(), nullable=True),
        sa.Column('permitted_roles', sa.Text(), nullable=True),
        sa.Column('sensitivity', sa.String(30), nullable=False, server_default='standard'),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table('activity_quarantine',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(60), nullable=False),
        sa.Column('source_event_id', sa.String(255), nullable=True),
        sa.Column('native_actor_id', sa.String(255), nullable=True),
        sa.Column('platform', sa.String(30), nullable=True),
        sa.Column('reason', sa.String(80), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('event_type', sa.String(80), nullable=True),
        sa.Column('action', sa.String(70), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payload_ref', sa.Text(), nullable=True),
    )
    op.create_index('ix_quarantine_source_event', 'activity_quarantine', ['source', 'source_event_id'])

    # ── Quarterly review tables ───────────────────────────────────────────
    op.create_table('quarterly_review_cycles',
        sa.Column('id', sa.String(60), primary_key=True),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_days', sa.Integer(), nullable=False, server_default='90'),
        sa.Column('review_budget_pct', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('as_of', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, server_default='created'),
        sa.Column('mode', sa.String(30), nullable=False, server_default='hybrid'),
        sa.Column('total_accounts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('mandatory_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('selected_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('deferred_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('evidence_gap_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('model_versions', sa.Text(), nullable=True),
        sa.Column('frozen_config', sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('preview','created','in_review','closed','archived')", name='cycle_status_valid'),
        sa.CheckConstraint("mode IN ('hybrid','policy_only','ml_unavailable')", name='cycle_mode_valid'),
    )

    op.create_table('quarterly_account_reviews',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('cycle_id', sa.String(60), sa.ForeignKey('quarterly_review_cycles.id'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('platform', sa.String(30), nullable=True),
        sa.Column('priority', sa.String(30), nullable=False, server_default='deferred_candidate'),
        sa.Column('policy_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('policy_reasons', sa.Text(), nullable=True),
        sa.Column('ml_percentile', sa.Float(), nullable=True),
        sa.Column('ml_status', sa.String(60), nullable=True),
        sa.Column('ml_model_key', sa.String(30), nullable=True),
        sa.Column('ml_model_schema', sa.String(80), nullable=True),
        sa.Column('ml_model_trained_utc', sa.String(60), nullable=True),
        sa.Column('coverage_days', sa.Float(), nullable=True),
        sa.Column('coverage_known', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transfer_flag', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reason_codes', sa.Text(), nullable=True),
        sa.Column('state', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('decision', sa.String(40), nullable=True),
        sa.Column('decision_by', sa.String(120), nullable=True),
        sa.Column('decision_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_rationale', sa.Text(), nullable=True),
        sa.UniqueConstraint('cycle_id', 'account_id', name='uq_quarterly_review_cycle_account'),
        sa.CheckConstraint("priority IN ('mandatory','selected','deferred_candidate','insufficient_evidence','deprioritized_not_certified')", name='review_priority_valid'),
        sa.CheckConstraint("state IN ('pending','in_review','decided','closed')", name='review_state_valid'),
    )
    op.create_index('ix_quarterly_reviews_cycle', 'quarterly_account_reviews', ['cycle_id'])
    op.create_index('ix_quarterly_reviews_account', 'quarterly_account_reviews', ['account_id'])

    # ── CSV import tables ─────────────────────────────────────────────────
    op.create_table('review_outcome_import_batches',
        sa.Column('id', sa.String(60), primary_key=True),
        sa.Column('cycle_id', sa.String(60), sa.ForeignKey('quarterly_review_cycles.id'), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('file_sha256', sa.String(64), nullable=False),
        sa.Column('uploader', sa.String(120), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('committed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('template_scope', sa.String(30), nullable=False, server_default='review_queue'),
        sa.Column('total_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('valid_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('invalid_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duplicate_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(30), nullable=False, server_default='previewed'),
        sa.Column('validation_summary', sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('previewed','rejected','committed','expired')", name='import_batch_status_valid'),
        sa.CheckConstraint("template_scope IN ('full_population','review_queue')", name='import_scope_valid'),
    )

    op.create_table('review_outcome_import_rows',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('batch_id', sa.String(60), sa.ForeignKey('review_outcome_import_batches.id'), nullable=False),
        sa.Column('csv_row_number', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.String(255), nullable=True),
        sa.Column('platform', sa.String(30), nullable=True),
        sa.Column('reviewer_id', sa.String(120), nullable=True),
        sa.Column('reviewed_at_utc', sa.String(60), nullable=True),
        sa.Column('review_classification', sa.String(60), nullable=True),
        sa.Column('access_decision', sa.String(40), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('evidence_reference', sa.String(255), nullable=True),
        sa.Column('is_valid', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_code', sa.String(80), nullable=True),
        sa.Column('error_message', sa.String(500), nullable=True),
    )
    op.create_index('ix_import_rows_batch', 'review_outcome_import_rows', ['batch_id'])

    op.create_table('quarterly_review_outcomes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('cycle_id', sa.String(60), sa.ForeignKey('quarterly_review_cycles.id'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('platform', sa.String(30), nullable=False),
        sa.Column('reviewer_id', sa.String(120), nullable=False),
        sa.Column('reviewed_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('review_classification', sa.String(60), nullable=False),
        sa.Column('access_decision', sa.String(40), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('evidence_reference', sa.String(255), nullable=True),
        sa.Column('import_batch_id', sa.String(60), sa.ForeignKey('review_outcome_import_batches.id'), nullable=True),
        sa.Column('uploader', sa.String(120), nullable=True),
        sa.Column('approved_by', sa.String(120), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('superseded_by', sa.Integer(), nullable=True),
        sa.UniqueConstraint('cycle_id', 'account_id', name='uq_review_outcome_cycle_account'),
        sa.CheckConstraint("review_classification IN ('verified_normal','confirmed_behavioral_concern','confirmed_policy_concern','insufficient_evidence','not_applicable')", name='outcome_classification_valid'),
        sa.CheckConstraint("access_decision IN ('retain','request_revoke','request_reduce','defer','escalate')", name='outcome_decision_valid'),
    )

    # ── ML training provenance ────────────────────────────────────────────
    op.create_table('ml_training_runs',
        sa.Column('id', sa.String(60), primary_key=True),
        sa.Column('platform', sa.String(30), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, server_default='prepared'),
        sa.Column('model_schema', sa.String(80), nullable=False),
        sa.Column('artifact_hash', sa.String(64), nullable=True),
        sa.Column('feature_schema_version', sa.String(80), nullable=True),
        sa.Column('source_cycle_ids', sa.Text(), nullable=True),
        sa.Column('training_normal_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('training_concern_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('validation_report', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('approved_by', sa.String(120), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rollback_target', sa.String(60), nullable=True),
        sa.CheckConstraint("status IN ('prepared','training','trained','validated','approved','promoted','rolled_back','failed')", name='training_run_status_valid'),
    )


def downgrade():
    op.drop_table('ml_training_runs')
    op.drop_table('quarterly_review_outcomes')
    op.drop_index('ix_import_rows_batch', 'review_outcome_import_rows')
    op.drop_table('review_outcome_import_rows')
    op.drop_table('review_outcome_import_batches')
    op.drop_index('ix_quarterly_reviews_account', 'quarterly_account_reviews')
    op.drop_index('ix_quarterly_reviews_cycle', 'quarterly_account_reviews')
    op.drop_table('quarterly_account_reviews')
    op.drop_table('quarterly_review_cycles')
    op.drop_index('ix_quarantine_source_event', 'activity_quarantine')
    op.drop_table('activity_quarantine')
    op.drop_table('managed_resource_policies')
    op.drop_index('ix_transfers_identity', 'employee_transfers')
    op.drop_table('employee_transfers')
    op.drop_index('ix_ad_membership_identity', 'ad_group_membership_history')
    op.drop_table('ad_group_membership_history')
    op.drop_table('ad_group_catalog')
    op.drop_index('ix_coverage_platform_dates', 'activity_coverage')
    op.drop_table('activity_coverage')
    op.drop_index('ix_activity_event_type_occurred', 'activity_events')
    op.drop_column('activity_events', 'received_at')
    op.drop_column('activity_events', 'resource_key')
    op.drop_column('activity_events', 'device_id')
    op.drop_column('activity_events', 'event_type')
    op.drop_column('activity_events', 'source_event_id')
    op.drop_column('access_grants', 'sensitivity')
    op.drop_column('accounts', 'native_id_type')
    op.drop_column('accounts', 'native_id')
    op.drop_column('systems', 'platform')
