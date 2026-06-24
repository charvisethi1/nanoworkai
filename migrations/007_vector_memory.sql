-- Vector Memory System
-- Unified vector storage for embeddings, conversations, preferences, and scraped content

-- Enable pgvector extension if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop existing if migrating from old schema
DROP TABLE IF EXISTS vector_memory CASCADE;

-- Main vector memory table
CREATE TABLE vector_memory (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1024) NOT NULL,  -- Voyage-3 dimension, adjust if using different model
    metadata JSONB DEFAULT '{}'::jsonb,
    source TEXT NOT NULL,  -- 'conversation', 'user_preference', 'web_scrape', etc.
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    namespace TEXT NOT NULL,  -- Partition by user_id, project_id, or 'global'

    -- Indexes for fast lookups
    CONSTRAINT valid_source CHECK (source IN (
        'conversation',
        'user_preference',
        'user_memory',
        'web_scrape',
        'business_knowledge',
        'system'
    ))
);

-- Indexes for performance
CREATE INDEX idx_vector_memory_namespace ON vector_memory (namespace);
CREATE INDEX idx_vector_memory_source ON vector_memory (source);
CREATE INDEX idx_vector_memory_timestamp ON vector_memory (timestamp DESC);
CREATE INDEX idx_vector_memory_metadata_gin ON vector_memory USING gin (metadata);

-- Vector similarity index using HNSW (Hierarchical Navigable Small World)
-- This provides fast approximate nearest neighbor search
CREATE INDEX idx_vector_memory_embedding_hnsw ON vector_memory
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Alternative: IVFFlat index (faster build, slower search)
-- CREATE INDEX idx_vector_memory_embedding_ivf ON vector_memory
-- USING ivfflat (embedding vector_cosine_ops)
-- WITH (lists = 100);

-- RPC function for semantic search
CREATE OR REPLACE FUNCTION match_vector_memory(
    query_embedding vector(1024),
    match_namespace TEXT,
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 10,
    source_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    id TEXT,
    content TEXT,
    embedding vector(1024),
    metadata JSONB,
    source TEXT,
    timestamp TIMESTAMPTZ,
    namespace TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        vm.id,
        vm.content,
        vm.embedding,
        vm.metadata,
        vm.source,
        vm.timestamp,
        vm.namespace,
        1 - (vm.embedding <=> query_embedding) AS similarity
    FROM vector_memory vm
    WHERE vm.namespace = match_namespace
        AND (source_filter IS NULL OR vm.source = source_filter)
        AND 1 - (vm.embedding <=> query_embedding) >= match_threshold
    ORDER BY vm.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- RPC function for cross-namespace search (admin/global search)
CREATE OR REPLACE FUNCTION match_vector_memory_global(
    query_embedding vector(1024),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 10,
    namespace_filter TEXT DEFAULT NULL,
    source_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    id TEXT,
    content TEXT,
    embedding vector(1024),
    metadata JSONB,
    source TEXT,
    timestamp TIMESTAMPTZ,
    namespace TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        vm.id,
        vm.content,
        vm.embedding,
        vm.metadata,
        vm.source,
        vm.timestamp,
        vm.namespace,
        1 - (vm.embedding <=> query_embedding) AS similarity
    FROM vector_memory vm
    WHERE (namespace_filter IS NULL OR vm.namespace = namespace_filter)
        AND (source_filter IS NULL OR vm.source = source_filter)
        AND 1 - (vm.embedding <=> query_embedding) >= match_threshold
    ORDER BY vm.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function to get recent memories for a namespace
CREATE OR REPLACE FUNCTION get_recent_memories(
    target_namespace TEXT,
    source_filter TEXT DEFAULT NULL,
    limit_count INT DEFAULT 50
)
RETURNS TABLE (
    id TEXT,
    content TEXT,
    metadata JSONB,
    source TEXT,
    timestamp TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        vm.id,
        vm.content,
        vm.metadata,
        vm.source,
        vm.timestamp
    FROM vector_memory vm
    WHERE vm.namespace = target_namespace
        AND (source_filter IS NULL OR vm.source = source_filter)
    ORDER BY vm.timestamp DESC
    LIMIT limit_count;
END;
$$;

-- Function to delete old memories (cleanup)
CREATE OR REPLACE FUNCTION cleanup_old_memories(
    days_old INT DEFAULT 90,
    exclude_sources TEXT[] DEFAULT ARRAY['user_preference']::TEXT[]
)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM vector_memory
    WHERE timestamp < NOW() - (days_old || ' days')::INTERVAL
        AND NOT (source = ANY(exclude_sources));

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

-- Function to get memory stats
CREATE OR REPLACE FUNCTION vector_memory_stats()
RETURNS TABLE (
    total_memories BIGINT,
    by_source JSONB,
    by_namespace_count BIGINT,
    oldest_memory TIMESTAMPTZ,
    newest_memory TIMESTAMPTZ,
    avg_embedding_size INT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*) as total_memories,
        jsonb_object_agg(source, cnt) as by_source,
        COUNT(DISTINCT namespace) as by_namespace_count,
        MIN(timestamp) as oldest_memory,
        MAX(timestamp) as newest_memory,
        AVG(array_length(embedding::real[], 1))::INT as avg_embedding_size
    FROM (
        SELECT source, COUNT(*) as cnt, timestamp, embedding, namespace
        FROM vector_memory
        GROUP BY source, timestamp, embedding, namespace
    ) subq;
END;
$$;

-- Example data for testing (optional - comment out for production)
-- INSERT INTO vector_memory (id, content, embedding, metadata, source, namespace) VALUES
-- ('test_1', 'User prefers subscription pricing', vector(array_fill(0.1::float, ARRAY[1024])), '{"key": "pricing_preference"}', 'user_preference', 'user_test123'),
-- ('test_2', 'Business is a SaaS platform for project management', vector(array_fill(0.2::float, ARRAY[1024])), '{"business": "PM tool"}', 'business_knowledge', 'global'),
-- ('test_3', 'User: I want subscription pricing. Assistant: Great choice!', vector(array_fill(0.3::float, ARRAY[1024])), '{}', 'conversation', 'user_test123');

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON vector_memory TO authenticated;
GRANT EXECUTE ON FUNCTION match_vector_memory TO authenticated;
GRANT EXECUTE ON FUNCTION match_vector_memory_global TO authenticated;
GRANT EXECUTE ON FUNCTION get_recent_memories TO authenticated;
GRANT EXECUTE ON FUNCTION vector_memory_stats TO authenticated;
GRANT EXECUTE ON FUNCTION cleanup_old_memories TO service_role;  -- Only service role can cleanup

-- Comments for documentation
COMMENT ON TABLE vector_memory IS 'Unified vector storage for embeddings, conversations, and knowledge';
COMMENT ON COLUMN vector_memory.id IS 'Unique identifier (often namespace_source_contenthash)';
COMMENT ON COLUMN vector_memory.content IS 'Original text content before embedding';
COMMENT ON COLUMN vector_memory.embedding IS 'Vector embedding (default 1024-d for Voyage-3)';
COMMENT ON COLUMN vector_memory.metadata IS 'Flexible JSON metadata (user_id, url, chunk_index, etc.)';
COMMENT ON COLUMN vector_memory.source IS 'Source type for filtering (conversation, web_scrape, etc.)';
COMMENT ON COLUMN vector_memory.namespace IS 'Isolation boundary (user_id, project_id, or global)';

COMMENT ON FUNCTION match_vector_memory IS 'Semantic search within a namespace using cosine similarity';
COMMENT ON FUNCTION match_vector_memory_global IS 'Semantic search across all namespaces (admin use)';
COMMENT ON FUNCTION get_recent_memories IS 'Get recent memories by timestamp without vector search';
COMMENT ON FUNCTION cleanup_old_memories IS 'Delete memories older than X days (excludes preferences)';
COMMENT ON FUNCTION vector_memory_stats IS 'Get statistics about stored memories';
