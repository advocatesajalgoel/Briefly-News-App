"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-09-05 20:48:57.509046
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('categories',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=48), nullable=False),
    sa.Column('name', sa.String(length=96), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('keywords', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_synthetic', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('pipeline_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('podcast_episodes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('slug', sa.String(length=180), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('subtitle', sa.Text(), nullable=True),
    sa.Column('edition_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('script', sa.Text(), nullable=False),
    sa.Column('script_segments', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('script_word_count', sa.Integer(), nullable=False),
    sa.Column('estimated_duration_seconds', sa.Integer(), nullable=False),
    sa.Column('audio_url', sa.Text(), nullable=True),
    sa.Column('audio_duration_seconds', sa.Integer(), nullable=True),
    sa.Column('audio_bytes', sa.Integer(), nullable=True),
    sa.Column('audio_mime_type', sa.String(length=64), nullable=True),
    sa.Column('tts_provider', sa.String(length=32), nullable=True),
    sa.Column('tts_voice', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('qc_report', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_podcast_episodes_published_at'), 'podcast_episodes', ['published_at'], unique=False)
    op.create_index(op.f('ix_podcast_episodes_status'), 'podcast_episodes', ['status'], unique=False)
    op.create_table('sources',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('homepage_url', sa.Text(), nullable=True),
    sa.Column('feed_url', sa.Text(), nullable=True),
    sa.Column('domains', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('access', sa.String(length=24), nullable=False),
    sa.Column('country', sa.String(length=8), nullable=True),
    sa.Column('language', sa.String(length=12), nullable=False),
    sa.Column('is_independent', sa.Boolean(), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('fetch_interval_minutes', sa.Integer(), nullable=False),
    sa.Column('last_fetched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('consecutive_failures', sa.Integer(), nullable=False),
    sa.Column('feed_state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index('ix_sources_enabled_kind', 'sources', ['is_enabled', 'kind'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('device_id', sa.String(length=128), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('display_name', sa.String(length=120), nullable=True),
    sa.Column('preferred_categories', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('locale', sa.String(length=12), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('device_id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('stories',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('category_id', sa.UUID(), nullable=True),
    sa.Column('slug', sa.String(length=180), nullable=False),
    sa.Column('headline', sa.Text(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('summary_word_count', sa.Integer(), nullable=False),
    sa.Column('dek', sa.Text(), nullable=True),
    sa.Column('first_reported_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_reported_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_count', sa.Integer(), nullable=False),
    sa.Column('independent_source_count', sa.Integer(), nullable=False),
    sa.Column('diversity_level', sa.String(length=12), nullable=False),
    sa.Column('diversity_breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('has_official_source', sa.Boolean(), nullable=False),
    sa.Column('has_disputed_claims', sa.Boolean(), nullable=False),
    sa.Column('confidence', sa.String(length=16), nullable=False),
    sa.Column('rank_score', sa.Float(), nullable=False),
    sa.Column('rank_components', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('qc_report', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('centroid', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('entity_keys', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('summary_word_count <= 30', name='ck_stories_summary_max_30_words'),
    sa.CheckConstraint('summary_word_count >= 0', name='ck_stories_wordcount_nonneg'),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index('ix_stories_category_published', 'stories', ['category_id', 'published_at'], unique=False)
    op.create_index(op.f('ix_stories_first_reported_at'), 'stories', ['first_reported_at'], unique=False)
    op.create_index(op.f('ix_stories_last_reported_at'), 'stories', ['last_reported_at'], unique=False)
    op.create_index(op.f('ix_stories_published_at'), 'stories', ['published_at'], unique=False)
    op.create_index(op.f('ix_stories_rank_score'), 'stories', ['rank_score'], unique=False)
    op.create_index(op.f('ix_stories_status'), 'stories', ['status'], unique=False)
    op.create_index('ix_stories_status_rank', 'stories', ['status', 'rank_score'], unique=False)
    op.create_table('articles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('source_id', sa.UUID(), nullable=False),
    sa.Column('story_id', sa.UUID(), nullable=True),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('canonical_url', sa.Text(), nullable=False),
    sa.Column('url_hash', sa.String(length=64), nullable=False),
    sa.Column('guid', sa.Text(), nullable=True),
    sa.Column('headline', sa.Text(), nullable=False),
    sa.Column('feed_summary', sa.Text(), nullable=True),
    sa.Column('author', sa.Text(), nullable=True),
    sa.Column('language', sa.String(length=12), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('discovery_channel', sa.String(length=32), nullable=False),
    sa.Column('discovery_query', sa.String(length=160), nullable=True),
    sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('fingerprint', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('embedding', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id', 'url_hash', name='uq_articles_source_url')
    )
    op.create_index(op.f('ix_articles_published_at'), 'articles', ['published_at'], unique=False)
    op.create_index('ix_articles_status_published', 'articles', ['status', 'published_at'], unique=False)
    op.create_index('ix_articles_story', 'articles', ['story_id'], unique=False)
    op.create_table('bookmarks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('story_id', sa.UUID(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'story_id', name='uq_bookmarks_user_story')
    )
    op.create_table('podcast_stories',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('episode_id', sa.UUID(), nullable=False),
    sa.Column('story_id', sa.UUID(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('segment_title', sa.Text(), nullable=True),
    sa.Column('narration', sa.Text(), nullable=False),
    sa.Column('word_count', sa.Integer(), nullable=False),
    sa.Column('start_offset_seconds', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['episode_id'], ['podcast_episodes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('episode_id', 'story_id', name='uq_podcast_stories_episode_story')
    )
    op.create_index('ix_podcast_stories_episode_pos', 'podcast_stories', ['episode_id', 'position'], unique=False)
    op.create_table('extracted_facts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('story_id', sa.UUID(), nullable=False),
    sa.Column('article_id', sa.UUID(), nullable=True),
    sa.Column('source_id', sa.UUID(), nullable=True),
    sa.Column('slot', sa.String(length=16), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('attributed_to', sa.Text(), nullable=True),
    sa.Column('evidence', sa.Text(), nullable=True),
    sa.Column('support_count', sa.Integer(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('salience', sa.Float(), nullable=False),
    sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('confidence >= 0 AND confidence <= 1', name='ck_facts_confidence_range'),
    sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_facts_story_slot', 'extracted_facts', ['story_id', 'slot'], unique=False)
    op.create_table('story_sources',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('story_id', sa.UUID(), nullable=False),
    sa.Column('source_id', sa.UUID(), nullable=False),
    sa.Column('article_id', sa.UUID(), nullable=True),
    sa.Column('source_name', sa.String(length=160), nullable=False),
    sa.Column('source_kind', sa.String(length=24), nullable=False),
    sa.Column('original_headline', sa.Text(), nullable=False),
    sa.Column('original_url', sa.Text(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_primary_source', sa.Boolean(), nullable=False),
    sa.Column('similarity', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('story_id', 'source_id', name='uq_story_sources_story_source')
    )


def downgrade() -> None:
    op.drop_table('story_sources')
    op.drop_index('ix_facts_story_slot', table_name='extracted_facts')
    op.drop_table('extracted_facts')
    op.drop_index('ix_podcast_stories_episode_pos', table_name='podcast_stories')
    op.drop_table('podcast_stories')
    op.drop_table('bookmarks')
    op.drop_index('ix_articles_story', table_name='articles')
    op.drop_index('ix_articles_status_published', table_name='articles')
    op.drop_index(op.f('ix_articles_published_at'), table_name='articles')
    op.drop_table('articles')
    op.drop_index('ix_stories_status_rank', table_name='stories')
    op.drop_index(op.f('ix_stories_status'), table_name='stories')
    op.drop_index(op.f('ix_stories_rank_score'), table_name='stories')
    op.drop_index(op.f('ix_stories_published_at'), table_name='stories')
    op.drop_index(op.f('ix_stories_last_reported_at'), table_name='stories')
    op.drop_index(op.f('ix_stories_first_reported_at'), table_name='stories')
    op.drop_index('ix_stories_category_published', table_name='stories')
    op.drop_table('stories')
    op.drop_table('users')
    op.drop_index('ix_sources_enabled_kind', table_name='sources')
    op.drop_table('sources')
    op.drop_index(op.f('ix_podcast_episodes_status'), table_name='podcast_episodes')
    op.drop_index(op.f('ix_podcast_episodes_published_at'), table_name='podcast_episodes')
    op.drop_table('podcast_episodes')
    op.drop_table('pipeline_runs')
    op.drop_table('categories')
