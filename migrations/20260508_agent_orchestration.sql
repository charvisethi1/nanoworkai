-- Agent orchestration and usage tracking tables

-- Agent usage logs for billing and monitoring
CREATE TABLE IF NOT EXISTS agent_usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('semi_autonomous', 'fully_autonomous', 'manual')),
    credits_used INTEGER NOT NULL DEFAULT 0,
    total_calls INTEGER NOT NULL DEFAULT 0,
    call_history JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Index for billing queries
    INDEX idx_agent_usage_phone_created (phone_number, created_at DESC)
);

-- User agent plan and credits
CREATE TABLE IF NOT EXISTS user_agent_plans (
    phone_number TEXT PRIMARY KEY,
    plan_type TEXT NOT NULL CHECK (plan_type IN ('semi_autonomous', 'fully_autonomous', 'manual')),
    credits_total INTEGER NOT NULL DEFAULT 100,
    credits_used INTEGER NOT NULL DEFAULT 0,
    credits_remaining INTEGER NOT NULL GENERATED ALWAYS AS (credits_total - credits_used) STORED,
    auto_recharge BOOLEAN NOT NULL DEFAULT FALSE,
    recharge_threshold INTEGER NOT NULL DEFAULT 10,
    recharge_amount INTEGER NOT NULL DEFAULT 100,
    upgraded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Agent approval queue (for semi-autonomous mode)
CREATE TABLE IF NOT EXISTS agent_approval_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    requesting_agent TEXT,
    context JSONB NOT NULL,
    credits_cost INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    approved_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '15 minutes'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    INDEX idx_approval_queue_phone_status (phone_number, status, created_at DESC)
);

-- RLS policies
ALTER TABLE agent_usage_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_agent_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_approval_queue ENABLE ROW LEVEL SECURITY;

-- Users can view their own usage
CREATE POLICY agent_usage_user_read ON agent_usage_logs
    FOR SELECT
    USING (phone_number = current_setting('request.phone_number', true)::text);

-- Users can view their own plan
CREATE POLICY agent_plan_user_read ON user_agent_plans
    FOR SELECT
    USING (phone_number = current_setting('request.phone_number', true)::text);

-- Users can view their own approval queue
CREATE POLICY agent_approval_user_read ON agent_approval_queue
    FOR SELECT
    USING (phone_number = current_setting('request.phone_number', true)::text);

-- Users can update their approval queue
CREATE POLICY agent_approval_user_update ON agent_approval_queue
    FOR UPDATE
    USING (phone_number = current_setting('request.phone_number', true)::text);

-- Function to deduct credits
CREATE OR REPLACE FUNCTION deduct_agent_credits(
    p_phone_number TEXT,
    p_credits INTEGER
) RETURNS BOOLEAN AS $$
DECLARE
    v_remaining INTEGER;
BEGIN
    -- Update credits_used atomically
    UPDATE user_agent_plans
    SET credits_used = credits_used + p_credits,
        updated_at = NOW()
    WHERE phone_number = p_phone_number
      AND credits_remaining >= p_credits
    RETURNING credits_remaining INTO v_remaining;

    -- Return true if update succeeded
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to auto-recharge credits
CREATE OR REPLACE FUNCTION auto_recharge_credits() RETURNS TRIGGER AS $$
BEGIN
    -- Check if auto-recharge is enabled and threshold reached
    IF NEW.auto_recharge = TRUE AND NEW.credits_remaining <= NEW.recharge_threshold THEN
        -- Add recharge amount
        NEW.credits_total := NEW.credits_total + NEW.recharge_amount;

        -- Log the recharge event
        INSERT INTO agent_usage_logs (phone_number, mode, credits_used, total_calls, call_history)
        VALUES (NEW.phone_number, 'auto_recharge', -NEW.recharge_amount, 0, '[]'::jsonb);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_auto_recharge
    BEFORE UPDATE ON user_agent_plans
    FOR EACH ROW
    EXECUTE FUNCTION auto_recharge_credits();

-- Seed default plans for existing users
INSERT INTO user_agent_plans (phone_number, plan_type, credits_total)
SELECT DISTINCT phone_number, 'semi_autonomous', 100
FROM nano_waitlist
WHERE phone_number IS NOT NULL
ON CONFLICT (phone_number) DO NOTHING;
