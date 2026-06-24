-- Carta Extraction Pipeline: PostgreSQL Database Schema
-- Multi-tenant architecture using 'tenant_id' for logical isolation

BEGIN;

-- ENUMS
CREATE TYPE entity_type AS ENUM ('Fund', 'SPV', 'Portfolio Company', 'Investor/LP', 'GP Entity', 'Fund Family', 'Management Company', 'Other');
CREATE TYPE job_status AS ENUM ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED');

-- CORE ENTITIES
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    external_org_pk VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, external_org_pk)
);

CREATE TABLE funds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    external_fund_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    type entity_type NOT NULL,
    general_ledger_enabled BOOLEAN DEFAULT FALSE,
    in_app_valuations_enabled BOOLEAN DEFAULT FALSE,
    raw_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, external_fund_id)
);

CREATE TABLE portfolio_companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    external_company_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(100),
    raw_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, external_company_id)
);

CREATE TABLE investors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    external_investor_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    raw_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, external_investor_id)
);

-- SECURITIES & CAP TABLE
CREATE TABLE securities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    company_id UUID REFERENCES portfolio_companies(id) ON DELETE CASCADE,
    owner_investor_id UUID REFERENCES investors(id) ON DELETE SET NULL,
    owner_fund_id UUID REFERENCES funds(id) ON DELETE SET NULL,
    external_security_id VARCHAR(255) NOT NULL,
    label VARCHAR(100),
    issue_date DATE,
    issuable_type VARCHAR(100),
    stock_type VARCHAR(100),
    status VARCHAR(50),
    currency VARCHAR(10),
    quantity DECIMAL(20,4) DEFAULT 0,
    cost DECIMAL(20,4) DEFAULT 0,
    value DECIMAL(20,4) DEFAULT 0,
    has_vesting BOOLEAN DEFAULT FALSE,
    qsbs_eligible BOOLEAN DEFAULT FALSE,
    raw_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, external_security_id)
);

-- VALUATIONS
CREATE TABLE valuations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    company_id UUID REFERENCES portfolio_companies(id) ON DELETE CASCADE,
    valuation_date DATE NOT NULL,
    pre_money_valuation DECIMAL(20,4),
    post_money_valuation DECIMAL(20,4),
    currency VARCHAR(10),
    raw_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- DOCUMENTS
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    entity_id UUID NOT NULL, -- Polymorphic relation (Fund, Company, Security)
    entity_type entity_type NOT NULL,
    document_name VARCHAR(255) NOT NULL,
    document_url TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- GRAPH RELATIONSHIPS
CREATE TABLE relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_entity_id UUID NOT NULL,
    source_entity_type entity_type NOT NULL,
    target_entity_id UUID NOT NULL,
    target_entity_type entity_type NOT NULL,
    relationship_type VARCHAR(100) NOT NULL, -- e.g., 'HAS_MANY', 'OWNED_BY'
    evidence_source TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, source_entity_id, target_entity_id, relationship_type)
);

-- SYSTEM LOGS & JOBS
CREATE TABLE extraction_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    status job_status DEFAULT 'PENDING',
    target_entity_id VARCHAR(255),
    target_entity_type VARCHAR(100),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    total_entities_extracted INT DEFAULT 0,
    error_log TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- INDEXES FOR PERFORMANCE AND TENANT ISOLATION
CREATE INDEX idx_funds_tenant ON funds(tenant_id);
CREATE INDEX idx_companies_tenant ON portfolio_companies(tenant_id);
CREATE INDEX idx_securities_tenant_company ON securities(tenant_id, company_id);
CREATE INDEX idx_valuations_tenant_company ON valuations(tenant_id, company_id);
CREATE INDEX idx_securities_raw_json ON securities USING GIN(raw_metadata);

COMMIT;
