-- 创建数据库表结构

CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    current_turn_id VARCHAR(255),
    redo_stack JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS turns (
    turn_id VARCHAR(255) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id),
    parent_turn_id VARCHAR(255),
    user_instruction TEXT NOT NULL,
    intent VARCHAR(100),
    edit_scope VARCHAR(100),
    rewritten_prompt TEXT,
    negative_prompt TEXT,
    preservation_constraints JSONB DEFAULT '[]',
    input_image_id VARCHAR(255),
    output_image_id VARCHAR(255),
    mask_image_id VARCHAR(255),
    reference_image_ids JSONB DEFAULT '[]',
    model_provider VARCHAR(100),
    model_name VARCHAR(255),
    selected_tool VARCHAR(100),
    model_params JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'queued',
    qa_score FLOAT,
    qa_passed BOOLEAN,
    qa_result JSONB DEFAULT '{}',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS images (
    image_id VARCHAR(255) PRIMARY KEY,
    url TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    thumbnail_url TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id VARCHAR(255) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    turn_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'queued',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS model_calls (
    call_id VARCHAR(255) PRIMARY KEY,
    session_id VARCHAR(255),
    turn_id VARCHAR(255),
    provider VARCHAR(100) NOT NULL,
    model_name VARCHAR(255) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    purpose VARCHAR(100) NOT NULL,
    latency_ms INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL,
    error_message TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_turns_session_id ON turns(session_id);
CREATE INDEX idx_turns_parent_turn_id ON turns(parent_turn_id);
CREATE INDEX idx_jobs_session_id ON jobs(session_id);
CREATE INDEX idx_jobs_turn_id ON jobs(turn_id);
CREATE INDEX idx_model_calls_session_id ON model_calls(session_id);
CREATE INDEX idx_model_calls_turn_id ON model_calls(turn_id);
