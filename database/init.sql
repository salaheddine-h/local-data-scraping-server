CREATE TABLE IF NOT EXISTS datasets (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    content TEXT,
    raw_payload JSONB,
    cleaned_payload JSONB,
    status TEXT NOT NULL DEFAULT 'processed',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_datasets_created_at ON datasets (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_datasets_task_id ON datasets (task_id);
CREATE INDEX IF NOT EXISTS idx_datasets_source ON datasets (source);
CREATE INDEX IF NOT EXISTS idx_datasets_status ON datasets (status);