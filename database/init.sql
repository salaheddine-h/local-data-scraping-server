CREATE TABLE IF NOT EXISTS scraped_data (
    id SERIAL PRIMARY KEY,
    url TEXT,
    title TEXT,
    description TEXT,
    headings JSONB,
    links JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);