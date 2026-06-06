CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(3072),
    metadata JSONB,
    user_id INTEGER REFERENCES users(id)
);

CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    system_prompt TEXT NOT NULL DEFAULT '',
    user_profile TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP DEFAULT NOW()
);
