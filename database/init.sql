CREATE TABLE IF NOT EXISTS scraped_data (
    id SERIAL PRIMARY KEY,
    url TEXT,
    title TEXT,
    description TEXT,
    content TEXT,
    headings JSONB,
    links JSONB,
    matches JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE scraped_data ADD COLUMN IF NOT EXISTS content TEXT;
ALTER TABLE scraped_data ADD COLUMN IF NOT EXISTS matches JSONB DEFAULT '[]'::jsonb;
ALTER TABLE scraped_data ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;