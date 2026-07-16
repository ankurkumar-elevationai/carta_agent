// ─── State ───
let DATA = null;
let activeExplorerTab = 'ui';

// ─── Init ───
async function init() {
    try {
        const res = await fetch('data/business_data.json');
        DATA = await res.json();
        renderSidebar();
        renderOverview();
        renderFunds();
        renderSPVs();
        renderInvestments();
        renderInvestors();
        renderDocuments();
        renderExports();
        renderEntityGraph();
        renderPipeline();
        renderRelationships();
        renderTesting();
        setupNav();
        setupModal();
        setupPlatformApiExplorer();
    } catch (err) {
        console.error('Failed to load business data:', err);
        document.getElementById('main').innerHTML = `
            <div class="empty-state" style="margin-top:4rem;">
                <p style="font-size:1.2rem; margin-bottom:0.5rem;">Could not load business data.</p>
                <p>Run: <code>python scripts/export_frontend_data.py</code></p>
                <p style="margin-top:0.25rem;">Then: <code>python -m http.server 8080</code> from /frontend</p>
            </div>`;
    }
}

// ─── Sidebar ───
function renderSidebar() {
    const firm = DATA.firm || {};
    let name = firm.name || 'Carta Demo Dashboard';
    if (name === 'Krakatoa Ventures' || name === 'Unknown Firm') {
        name = 'Carta Demo Dashboard';
    }
    document.getElementById('firmName').textContent = name;
    document.getElementById('firmAdmin').textContent = firm.admin ? `${firm.admin} · ${firm.title || ''}` : '';
    document.getElementById('fileCount').textContent = DATA.summary.files_processed || 0;
}

// ─── Navigation ───
function setupNav() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            const sec = link.dataset.section;
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            link.classList.add('active');
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            document.getElementById('sec-' + sec).classList.add('active');
        });
    });

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', e => {
            const sub = btn.dataset.subtab;
            btn.parentElement.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const section = btn.closest('.section');
            section.querySelectorAll('.subtab-content').forEach(c => c.classList.remove('active'));
            section.querySelector('#subtab-' + sub).classList.add('active');
        });
    });
}

// ─── Overview ───
function renderOverview() {
    const s = DATA.summary;
    const kpis = [
        { value: s.total_funds, label: 'Funds', color: 'var(--accent-blue)' },
        { value: s.total_spvs, label: 'SPVs', color: 'var(--accent-rose)' },
        { value: s.total_investments, label: 'Investments', color: 'var(--accent-emerald)' },
        { value: s.total_investors, label: 'Investors', color: 'var(--accent-violet)' },
        { value: s.total_companies_with_profiles || 0, label: 'Company Profiles', color: 'var(--accent-cyan)' },
        { value: s.total_companies_with_409a || 0, label: '409A Valuations', color: 'var(--accent-amber)' },
        { value: s.total_securities || 0, label: 'Securities', color: '#6ee7b7' },
        { value: s.total_contacts || 0, label: 'Contacts', color: '#93c5fd' },
    ];
    document.getElementById('kpiRow').innerHTML = kpis.map(k => `
        <div class="kpi-card">
            <div class="kpi-value" style="color:${k.color}">${k.value}</div>
            <div class="kpi-label">${k.label}</div>
        </div>
    `).join('');

    // Top investors bar chart
    const topInvestors = (DATA.investors || []).slice(0, 10);
    const maxOwnership = topInvestors.length > 0 ? Math.max(...topInvestors.map(i => i.total_ownership_pct)) : 1;
    document.getElementById('topInvestorsList').innerHTML = topInvestors.map(inv => {
        const pct = inv.total_ownership_pct;
        const barWidth = Math.min((pct / maxOwnership) * 100, 100);
        return `
            <div class="investor-bar-row">
                <div class="investor-bar-name" title="${inv.name}">${inv.name}</div>
                <div class="investor-bar-track"><div class="investor-bar-fill" style="width:${barWidth}%"></div></div>
                <div class="investor-bar-pct">${pct.toFixed(2)}%</div>
            </div>`;
    }).join('') || '<p class="empty-state">No investor data.</p>';

    // Fund structure hierarchy
    const structure = DATA.fund_structure || [];
    if (structure.length > 0) {
        document.getElementById('fundBreakdownChart').innerHTML = structure.map(group => `
            <div class="breakdown-row" style="border-bottom:none; padding-bottom:0.2rem;">
                <div class="breakdown-label" style="font-weight:700; color:var(--accent-blue)">${group.header}</div>
                <div class="breakdown-value" style="color:var(--text-secondary)">${(group.items || []).length}</div>
            </div>
            ${(group.items || []).map(item => `
                <div class="breakdown-row" style="padding-left:1.5rem;">
                    <div class="breakdown-label"><div class="breakdown-dot" style="background:${item.type === 'SPV' ? 'var(--accent-rose)' : item.type === 'General Partner' ? 'var(--accent-violet)' : 'var(--accent-blue)'}"></div>${item.legal_name}</div>
                    <div style="font-size:0.75rem; color:var(--text-muted)">${item.type}</div>
                </div>
            `).join('')}
        `).join('');
    } else {
        // Fallback to simple breakdown
        const breakdown = [
            { label: 'Funds', count: s.total_funds, color: 'var(--accent-blue)' },
            { label: 'SPVs', count: s.total_spvs, color: 'var(--accent-rose)' },
            { label: 'Investments', count: s.total_investments, color: 'var(--accent-emerald)' },
            { label: 'IRR Tracked', count: s.total_companies_with_irr || 0, color: 'var(--accent-violet)' },
        ];
        document.getElementById('fundBreakdownChart').innerHTML = breakdown.map(b => `
            <div class="breakdown-row">
                <div class="breakdown-label"><div class="breakdown-dot" style="background:${b.color}"></div>${b.label}</div>
                <div class="breakdown-value" style="color:${b.color}">${b.count}</div>
            </div>
        `).join('');
    }

    // Recent cap tables
    const capEntries = Object.entries(DATA.cap_tables || {}).slice(0, 6);
    if (capEntries.length > 0) {
        document.getElementById('recentCapTables').innerHTML = `
            <table class="data-table">
                <thead><tr><th>Company</th><th>Stakeholders</th><th>Top Holder</th><th>Top Ownership</th></tr></thead>
                <tbody>${capEntries.map(([company, stakeholders]) => {
                    const top = stakeholders.reduce((a, b) => a.total_ownership_pct > b.total_ownership_pct ? a : b, stakeholders[0]);
                    return `<tr>
                        <td><strong>${company}</strong></td>
                        <td>${stakeholders.length}</td>
                        <td>${top.stakeholder}</td>
                        <td style="color:var(--accent-emerald); font-weight:600">${top.total_ownership_pct.toFixed(2)}%</td>
                    </tr>`;
                }).join('')}</tbody>
            </table>`;
    } else {
        document.getElementById('recentCapTables').innerHTML = '<p class="empty-state">No cap table data captured.</p>';
    }
}

// ─── Funds ───
function renderFunds() {
    const allFunds = DATA.funds || [];
    document.getElementById('fundsCount').textContent = allFunds.length;
    const tbody = document.querySelector('#fundsTable tbody');
    tbody.innerHTML = allFunds.map(f => {
        const badgeCls = getBadgeClass(f.type);
        const perms = (f.permissions || []).map(p => `<span class="perm-pill">${p}</span>`).join(' ');
        return `<tr>
            <td><strong>${f.name}</strong></td>
            <td><span class="type-badge ${badgeCls}">${f.type}</span></td>
            <td class="cell-mono">${(f.uuid || '').substring(0, 8)}…</td>
            <td>${perms || '—'}</td>
        </tr>`;
    }).join('');
}

// ─── SPVs ───
function renderSPVs() {
    const allSpvs = DATA.spvs || [];
    document.getElementById('spvsCount').textContent = allSpvs.length;
    const tbody = document.querySelector('#spvsTable tbody');
    tbody.innerHTML = allSpvs.map(f => {
        const perms = (f.permissions || []).map(p => `<span class="perm-pill">${p}</span>`).join(' ');
        return `<tr>
            <td><strong>${f.name}</strong></td>
            <td><span class="type-badge spv">SPV</span></td>
            <td class="cell-mono">${(f.uuid || '').substring(0, 8)}…</td>
            <td>${perms || '—'}</td>
        </tr>`;
    }).join('');
}

// ─── Investments ───
function renderInvestments() {
    const investments = DATA.investments || [];
    document.getElementById('investmentsCount').textContent = investments.length;
    const grid = document.getElementById('investmentsGrid');
    grid.innerHTML = investments.map((inv, idx) => {
        const val = inv.valuation || {};
        const profile = inv.profile || {};
        const hd = inv.holdings_summary || {};
        const irr = inv.irr || {};
        const stakeholders = (inv.cap_table || []).slice(0, 3);
        const fmvCount = (inv.fmv_409a || []).length;
        const contactCount = (inv.contacts || []).length;
        const secCount = (inv.securities || []).length;

        // Build info pills
        const pills = [];
        if (fmvCount) pills.push(`<span class="info-pill fmv">${fmvCount} FMVs</span>`);
        if (contactCount) pills.push(`<span class="info-pill contact">${contactCount} contacts</span>`);
        if (secCount) pills.push(`<span class="info-pill sec">${secCount} securities</span>`);
        if (irr.irr_percentage !== undefined && irr.irr_percentage !== null) pills.push(`<span class="info-pill irr">IRR: ${Number(irr.irr_percentage).toFixed(1)}%</span>`);

        return `
            <div class="inv-card" data-idx="${idx}">
                <div class="inv-card-header">
                    <div>
                        <div class="inv-company-name">${inv.company}</div>
                        ${profile.legal_name && profile.legal_name !== inv.company ? `<div class="inv-legal-name">${profile.legal_name}</div>` : ''}
                    </div>
                    <div class="inv-share-class">${val.share_class || inv.group_name || '—'}</div>
                </div>
                <div class="inv-metrics">
                    <div>
                        <div class="inv-metric-label">Post-Money</div>
                        <div class="inv-metric-value">${formatMoney(val.post_money, val.currency)}</div>
                    </div>
                    <div>
                        <div class="inv-metric-label">Funds Raised</div>
                        <div class="inv-metric-value">${formatMoney(val.funds_raised, val.currency)}</div>
                    </div>
                    <div>
                        <div class="inv-metric-label">Ownership</div>
                        <div class="inv-metric-value">${hd.ownership_pct ? hd.ownership_pct.toFixed(2) + '%' : '—'}</div>
                    </div>
                    <div>
                        <div class="inv-metric-label">Multiple</div>
                        <div class="inv-metric-value">${irr.multiple ? irr.multiple.toFixed(2) + 'x' : '—'}</div>
                    </div>
                </div>
                ${pills.length ? `<div class="inv-pills">${pills.join('')}</div>` : ''}
                ${profile.ceo ? `<div class="inv-ceo"><span class="inv-metric-label">CEO</span> ${profile.ceo}</div>` : ''}
                ${profile.address ? `<div class="inv-address">${profile.address}</div>` : ''}
                ${stakeholders.length > 0 ? `
                <div class="inv-stakeholders">
                    <div class="inv-stakeholders-title">Top Stakeholders</div>
                    ${stakeholders.map(s => `
                        <div class="stakeholder-row">
                            <span class="name">${s.stakeholder}</span>
                            <span class="pct">${s.total_ownership_pct.toFixed(2)}%</span>
                        </div>
                    `).join('')}
                </div>` : ''}
            </div>`;
    }).join('');

    grid.querySelectorAll('.inv-card').forEach(card => {
        card.addEventListener('click', () => openInvestmentModal(parseInt(card.dataset.idx)));
    });
}

// ─── Investors ───
function renderInvestors() {
    const investors = DATA.investors || [];
    document.getElementById('investorsCount').textContent = investors.length;
    const tbody = document.querySelector('#investorsTable tbody');
    tbody.innerHTML = investors.map(inv => `
        <tr>
            <td><strong>${inv.name}</strong></td>
            <td style="color:var(--accent-emerald); font-weight:600">${inv.total_ownership_pct.toFixed(2)}%</td>
            <td class="cell-muted">${(inv.investments || []).join(', ') || '—'}</td>
        </tr>
    `).join('');
}

// ─── Documents ───
function renderDocuments() {
    const docs = DATA.documents || [];
    document.getElementById('documentsCount').textContent = docs.length;
    if (docs.length === 0) {
        document.getElementById('noDocsMsg').style.display = 'block';
        return;
    }
    const tbody = document.querySelector('#documentsTable tbody');
    tbody.innerHTML = docs.map(d => `
        <tr>
            <td><strong>${d.name}</strong></td>
            <td><span class="type-badge fund">${d.type}</span></td>
            <td>${d.date || '—'}</td>
            <td class="cell-muted">${d.fund_name || '—'}</td>
            <td class="cell-muted">${d.stakeholder || '—'}</td>
        </tr>
    `).join('');
}

// ─── Export Records ───
function renderExports() {
    const exports = DATA.export_records || [];
    document.getElementById('exportsCount').textContent = exports.length;
    if (exports.length === 0) {
        document.getElementById('noExportsMsg').style.display = 'block';
        return;
    }
    const tbody = document.querySelector('#exportsTable tbody');
    tbody.innerHTML = exports.map(e => `
        <tr>
            <td><strong>${e.entity_id || '—'}</strong></td>
            <td><span class="type-badge ${e.business_domain === 'capital_calls' ? 'gp' : 'fund'}">${e.business_domain}</span></td>
            <td><span class="perm-pill">${(e.file_format || 'csv').toUpperCase()}</span></td>
            <td class="cell-muted" style="max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${e.source_url}">${e.source_url || '—'}</td>
            <td><strong>${e.row_count || 0}</strong></td>
        </tr>
    `).join('');
}

// ─── Investment Detail Modal ───
function openInvestmentModal(idx) {
    const inv = DATA.investments[idx];
    if (!inv) return;
    const val = inv.valuation || {};
    const profile = inv.profile || {};
    const hd = inv.holdings_summary || {};
    const irr = inv.irr || {};

    document.getElementById('modalCompanyName').textContent = inv.company;

    // Company Profile
    const profileHTML = profile.legal_name ? `
        <div class="modal-section">
            <h3>Company Profile</h3>
            <div class="modal-props">
                <div class="modal-prop"><div class="label">Legal Name</div><div class="value">${profile.legal_name || '—'}</div></div>
                <div class="modal-prop"><div class="label">Incorporated</div><div class="value">${profile.date_of_incorporation || '—'}</div></div>
                <div class="modal-prop"><div class="label">CEO</div><div class="value">${profile.ceo || '—'}</div></div>
                <div class="modal-prop"><div class="label">Address</div><div class="value" style="font-size:0.82rem">${profile.address || '—'}</div></div>
                <div class="modal-prop"><div class="label">Website</div><div class="value">${profile.website ? `<a href="${profile.website}" target="_blank" style="color:var(--accent-blue)">${profile.website}</a>` : '—'}</div></div>
                <div class="modal-prop"><div class="label">Description</div><div class="value" style="font-size:0.82rem">${profile.description || '—'}</div></div>
            </div>
        </div>` : '';

    // Valuation + Performance
    document.getElementById('modalValuation').innerHTML = `
        <div class="modal-props">
            <div class="modal-prop"><div class="label">Post-Money</div><div class="value">${formatMoney(val.post_money, val.currency)}</div></div>
            <div class="modal-prop"><div class="label">Funds Raised</div><div class="value">${formatMoney(val.funds_raised, val.currency)}</div></div>
            <div class="modal-prop"><div class="label">Share Class</div><div class="value">${val.share_class || '—'}</div></div>
            <div class="modal-prop"><div class="label">Ownership</div><div class="value" style="color:var(--accent-emerald)">${hd.ownership_pct ? hd.ownership_pct.toFixed(2) + '%' : '—'}</div></div>
            <div class="modal-prop"><div class="label">IRR</div><div class="value" style="color:var(--accent-amber)">${irr.irr_percentage != null ? irr.irr_percentage.toFixed(2) + '%' : '—'}</div></div>
            <div class="modal-prop"><div class="label">Multiple</div><div class="value">${irr.multiple ? irr.multiple.toFixed(2) + 'x' : '—'}</div></div>
        </div>`;

    // Insert profile before cap table
    const profileContainer = document.getElementById('modalProfile');
    if (profileContainer) profileContainer.innerHTML = profileHTML;

    // Cap Table
    const ct = inv.cap_table || [];
    if (ct.length > 0) {
        document.getElementById('modalCapTable').innerHTML = `
            <table>
                <thead><tr><th>Stakeholder</th><th>Ownership %</th><th>Shares</th><th>Cost Basis</th><th>Share Classes</th></tr></thead>
                <tbody>${ct.map(s => `
                    <tr>
                        <td><strong>${s.stakeholder}</strong></td>
                        <td style="color:var(--accent-emerald)">${s.total_ownership_pct.toFixed(2)}%</td>
                        <td>${s.total_shares ? s.total_shares.toLocaleString() : '—'}</td>
                        <td>${s.total_cost ? '$' + s.total_cost.toLocaleString() : '—'}</td>
                        <td>${(s.share_classes || []).map(sc => `<span class="perm-pill">${sc.class}: ${(sc.shares || 0).toLocaleString()}</span>`).join(' ') || '—'}</td>
                    </tr>
                `).join('')}</tbody>
            </table>`;
    } else {
        document.getElementById('modalCapTable').innerHTML = '<p class="empty-state">No cap table data.</p>';
    }

    // Securities
    const secs = inv.securities || [];
    const holdingsEl = document.getElementById('modalHoldings');
    if (secs.length > 0) {
        holdingsEl.innerHTML = `
            <table>
                <thead><tr><th>Security</th><th>Shares / Diluted</th><th>Ownership %</th><th>Cost</th><th>Source</th></tr></thead>
                <tbody>${secs.map(s => `
                    <tr>
                        <td><strong>${s.name || '—'}</strong></td>
                        <td>${(s.shares || s.fully_diluted) ? Number(s.shares || s.fully_diluted).toLocaleString() : '—'}</td>
                        <td style="color:var(--accent-emerald)">${s.ownership_pct ? Number(s.ownership_pct).toFixed(2) + '%' : '—'}</td>
                        <td>${s.cost_basis ? '$' + Number(s.cost_basis).toLocaleString() : '—'}</td>
                        <td class="cell-muted">${s.source || 'option_plan'}</td>
                    </tr>
                `).join('')}</tbody>
            </table>`;
    } else {
        holdingsEl.innerHTML = '<p class="empty-state">No securities data.</p>';
    }

    // 409A FMVs
    const fmvs = inv.fmv_409a || [];
    const fmvEl = document.getElementById('modalFMV');
    if (fmvEl) {
        if (fmvs.length > 0) {
            fmvEl.innerHTML = `
                <table>
                    <thead><tr><th>Date</th><th>Price</th><th>Currency</th><th>Common?</th><th>Primary?</th></tr></thead>
                    <tbody>${fmvs.map(f => `
                        <tr>
                            <td>${f.effective_date || '—'}</td>
                            <td style="color:var(--accent-emerald); font-weight:600">${f.price ? '$' + Number(f.price).toFixed(2) : '—'}</td>
                            <td>${f.currency || '—'}</td>
                            <td>${f.is_common ? '✓' : '—'}</td>
                            <td>${f.is_primary ? '✓' : '—'}</td>
                        </tr>
                    `).join('')}</tbody>
                </table>`;
        } else {
            fmvEl.innerHTML = '<p class="empty-state">No 409A FMV data.</p>';
        }
    }

    // Capital Transactions
    const txs = (inv.irr || {}).transactions || [];
    const txEl = document.getElementById('modalTransactions');
    if (txEl) {
        if (txs.length > 0) {
            txEl.innerHTML = `
                <table>
                    <thead><tr><th>Date</th><th>Type</th><th>Amount</th><th>Debit</th><th>Credit</th><th>Notes</th></tr></thead>
                    <tbody>${txs.slice(0, 50).map(t => `
                        <tr>
                            <td>${t.date || '—'}</td>
                            <td><strong>${t.type || '—'}</strong></td>
                            <td style="color:${t.amount < 0 ? 'var(--accent-rose)' : 'var(--accent-emerald)'}; font-weight:600">${t.amount ? (t.amount < 0 ? '-' : '') + '$' + Math.abs(t.amount).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '—'}</td>
                            <td>${t.debit ? (t.debit < 0 ? '-' : '') + '$' + Math.abs(t.debit).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '—'}</td>
                            <td>${t.credit ? (t.credit < 0 ? '-' : '') + '$' + Math.abs(t.credit).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '—'}</td>
                            <td class="cell-muted">${t.notes || '—'}</td>
                        </tr>
                    `).join('')}</tbody>
                </table>
                ${txs.length > 50 ? `<p style="font-size:0.75rem; color:var(--text-muted); margin-top:0.5rem;">Showing first 50 of ${txs.length} transactions.</p>` : ''}`;
        } else {
            txEl.innerHTML = '<p class="empty-state">No transaction records.</p>';
        }
    }

    // Contacts
    const cts = inv.contacts || [];
    const ctEl = document.getElementById('modalContacts');
    if (ctEl) {
        if (cts.length > 0) {
            ctEl.innerHTML = cts.map(c => `
                <div class="contact-row">
                    <span class="contact-name">${c.name || 'Unknown'}</span>
                    <span class="contact-email">${c.email || ''}</span>
                    ${c.is_primary ? '<span class="perm-pill" style="background:rgba(52,211,153,.15); color:var(--accent-emerald)">Primary</span>' : ''}
                </div>
            `).join('');
        } else {
            ctEl.innerHTML = '<p class="empty-state">No contacts.</p>';
        }
    }

    document.getElementById('investmentModal').classList.add('active');
}

function setupModal() {
    const modal = document.getElementById('investmentModal');
    document.getElementById('closeModal').addEventListener('click', () => modal.classList.remove('active'));
    modal.addEventListener('click', e => { if (e.target === modal) modal.classList.remove('active'); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') modal.classList.remove('active'); });
}

// ─── Helpers ───
function formatMoney(val, currency) {
    if (val === null || val === undefined) return '—';
    const c = currency || '$';
    if (val >= 1e9) return c + (val / 1e9).toFixed(2) + 'B';
    if (val >= 1e6) return c + (val / 1e6).toFixed(2) + 'M';
    if (val >= 1e3) return c + (val / 1e3).toFixed(1) + 'K';
    return c + val.toLocaleString();
}

function getBadgeClass(type) {
    const t = (type || '').toLowerCase();
    if (t === 'spv') return 'spv';
    if (t === 'general partner') return 'gp';
    if (t === 'management company') return 'mgmt';
    if (t === 'feeder fund') return 'feeder';
    if (t === 'fund') return 'fund';
    return 'entity';
}

// ─── Entity Graph (Canvas Force Layout) ───
function renderEntityGraph() {
    const graph = DATA.entity_graph || {};
    const nodes = graph.nodes || [];
    const edges = graph.edges || [];
    const summary = graph.summary || {};

    // Stats row
    const types = {};
    nodes.forEach(n => { types[n.type] = (types[n.type] || 0) + 1; });
    const edgeTypes = {};
    edges.forEach(e => { edgeTypes[e.type] = (edgeTypes[e.type] || 0) + 1; });

    document.getElementById('graphStats').innerHTML = [
        { v: summary.total_nodes || nodes.length, l: 'Nodes', c: 'var(--accent-blue)' },
        { v: summary.total_edges || edges.length, l: 'Edges', c: 'var(--accent-violet)' },
        ...Object.entries(types).map(([t, c]) => ({ v: c, l: t, c: t === 'organization' ? 'var(--accent-amber)' : t === 'fund' ? 'var(--accent-blue)' : t === 'spv' ? 'var(--accent-rose)' : 'var(--accent-emerald)' }))
    ].map(s => `<div class="graph-stat"><div class="graph-stat-value" style="color:${s.c}">${s.v}</div><div class="graph-stat-label">${s.l}</div></div>`).join('');

    // Legend
    const colorMap = { organization: '#fbbf24', fund: '#4f7cff', spv: '#f472b6', investment: '#34d399' };
    document.getElementById('graphLegend').innerHTML = Object.entries(colorMap).map(([type, color]) =>
        `<div class="graph-legend-item"><div class="graph-legend-dot" style="background:${color}"></div>${type}</div>`
    ).join('') + Object.entries(edgeTypes).map(([type, count]) =>
        `<div class="graph-legend-item" style="margin-left:1rem"><span style="color:var(--text-muted)">─</span> ${type} (${count})</div>`
    ).join('');

    // Canvas force-directed layout
    const canvas = document.getElementById('graphCanvas');
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width || 900;
    canvas.height = 500;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;

    if (nodes.length === 0) return;

    // Build adjacency
    const nodeMap = {};
    const simNodes = nodes.map((n, i) => {
        const sn = { id: n.id, type: n.type, name: n.name, x: W/2 + (Math.random() - 0.5) * W * 0.6, y: H/2 + (Math.random() - 0.5) * H * 0.6, vx: 0, vy: 0 };
        nodeMap[n.id] = sn;
        return sn;
    });
    const simEdges = edges.map(e => ({ source: nodeMap[e.source], target: nodeMap[e.target], type: e.type })).filter(e => e.source && e.target);

    function tick() {
        // Repulsion
        for (let i = 0; i < simNodes.length; i++) {
            for (let j = i + 1; j < simNodes.length; j++) {
                let dx = simNodes[j].x - simNodes[i].x;
                let dy = simNodes[j].y - simNodes[i].y;
                let dist = Math.sqrt(dx * dx + dy * dy) || 1;
                let force = 800 / (dist * dist);
                let fx = dx / dist * force;
                let fy = dy / dist * force;
                simNodes[i].vx -= fx; simNodes[i].vy -= fy;
                simNodes[j].vx += fx; simNodes[j].vy += fy;
            }
        }
        // Attraction
        simEdges.forEach(e => {
            let dx = e.target.x - e.source.x;
            let dy = e.target.y - e.source.y;
            let dist = Math.sqrt(dx * dx + dy * dy) || 1;
            let force = (dist - 80) * 0.01;
            let fx = dx / dist * force;
            let fy = dy / dist * force;
            e.source.vx += fx; e.source.vy += fy;
            e.target.vx -= fx; e.target.vy -= fy;
        });
        // Center gravity
        simNodes.forEach(n => {
            n.vx += (W / 2 - n.x) * 0.001;
            n.vy += (H / 2 - n.y) * 0.001;
            n.vx *= 0.85; n.vy *= 0.85;
            n.x += n.vx; n.y += n.vy;
            n.x = Math.max(20, Math.min(W - 20, n.x));
            n.y = Math.max(20, Math.min(H - 20, n.y));
        });
    }

    function draw() {
        ctx.clearRect(0, 0, W, H);
        // Edges
        ctx.lineWidth = 0.5;
        ctx.strokeStyle = 'rgba(79,124,255,0.2)';
        simEdges.forEach(e => {
            ctx.beginPath();
            ctx.moveTo(e.source.x, e.source.y);
            ctx.lineTo(e.target.x, e.target.y);
            ctx.stroke();
        });
        // Nodes
        simNodes.forEach(n => {
            const r = n.type === 'organization' ? 12 : n.type === 'fund' ? 8 : n.type === 'spv' ? 7 : 5;
            ctx.beginPath();
            ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
            ctx.fillStyle = colorMap[n.type] || '#34d399';
            ctx.fill();
            ctx.strokeStyle = 'rgba(255,255,255,0.15)';
            ctx.lineWidth = 1;
            ctx.stroke();
        });
        // Labels for large nodes
        ctx.font = '10px Inter, sans-serif';
        ctx.fillStyle = 'rgba(232,236,244,0.7)';
        ctx.textAlign = 'center';
        simNodes.forEach(n => {
            if (n.type === 'organization' || n.type === 'fund') {
                const label = (n.name || '').substring(0, 18);
                ctx.fillText(label, n.x, n.y - (n.type === 'organization' ? 16 : 12));
            }
        });
    }

    // Run simulation
    for (let i = 0; i < 200; i++) tick();
    draw();

    // Tooltip on hover
    canvas.addEventListener('mousemove', e => {
        const br = canvas.getBoundingClientRect();
        const mx = e.clientX - br.left, my = e.clientY - br.top;
        let hit = null;
        simNodes.forEach(n => {
            const r = n.type === 'organization' ? 12 : n.type === 'fund' ? 8 : 5;
            if (Math.hypot(n.x - mx, n.y - my) < r + 3) hit = n;
        });
        canvas.title = hit ? `${hit.name} (${hit.type})` : '';
        canvas.style.cursor = hit ? 'pointer' : 'grab';
    });
}

// ─── Pipeline Health ───
function renderPipeline() {
    const perf = DATA.performance_profile || {};
    const cov = DATA.coverage_report || {};
    const domains = DATA.domain_inventory || [];
    const schema = DATA.schema_summary || {};
    const replay = perf.replay_telemetry || {};
    const phases = perf.macro_phases || {};

    // KPIs
    const successRate = replay.endpoints_replayed ? ((replay.successful_replays / replay.endpoints_replayed) * 100).toFixed(1) : '—';
    const kpis = [
        { v: replay.endpoints_discovered || 0, l: 'APIs Discovered', c: 'var(--accent-blue)' },
        { v: replay.successful_replays || 0, l: 'Successful Replays', c: 'var(--accent-emerald)' },
        { v: replay.failed_replays || 0, l: 'Failed Replays', c: 'var(--accent-rose)' },
        { v: successRate + '%', l: 'Success Rate', c: 'var(--accent-amber)' },
        { v: Math.round(perf.total_duration_sec || 0) + 's', l: 'Total Runtime', c: 'var(--accent-violet)' },
        { v: replay.new_entities_found || 0, l: 'New Entities', c: 'var(--accent-cyan)' },
        { v: schema.total_clusters || 0, l: 'Schema Families', c: 'var(--accent-blue)' },
        { v: domains.length || cov.domains_discovered || 0, l: 'Domains Traversed', c: 'var(--accent-emerald)' },
    ];
    document.getElementById('pipelineKpis').innerHTML = kpis.map(k => `
        <div class="kpi-card">
            <div class="kpi-value" style="color:${k.c}">${k.v}</div>
            <div class="kpi-label">${k.l}</div>
        </div>
    `).join('');

    // Phase breakdown
    const maxPhase = Math.max(...Object.values(phases), 1);
    document.getElementById('phaseBreakdown').innerHTML = Object.entries(phases).map(([name, dur]) => {
        const pct = Math.max((dur / maxPhase) * 100, 2);
        return `<div class="phase-bar-row">
            <div class="phase-bar-label">${name}</div>
            <div class="phase-bar-track"><div class="phase-bar-fill" style="width:${pct}%">${dur.toFixed(1)}s</div></div>
        </div>`;
    }).join('') || '<p class="empty-state">No phase data.</p>';

    // Replay stats
    const discovered = replay.endpoints_discovered || 0;
    const replayed = replay.endpoints_replayed || 0;
    const skipped = replay.endpoints_skipped || 0;
    const success = replay.successful_replays || 0;
    const failed = replay.failed_replays || 0;
    document.getElementById('replayStats').innerHTML = `
        <div style="padding: 0.5rem 0;">
            ${[['Discovered', discovered, 'var(--accent-blue)'], ['Replayed', replayed, 'var(--accent-cyan)'], ['Skipped', skipped, 'var(--text-muted)'], ['Successful', success, 'var(--accent-emerald)'], ['Failed', failed, 'var(--accent-rose)']].map(([label, val, color]) => `
                <div style="display:flex; justify-content:space-between; padding:0.5rem 0; border-bottom:1px solid var(--border);">
                    <span style="color:var(--text-secondary)">${label}</span>
                    <span style="font-weight:700; color:${color}">${val}</span>
                </div>
            `).join('')}
        </div>`;

    // ROI grid
    const roi = perf.replay_roi_metrics || {};
    document.getElementById('roiGrid').innerHTML = Object.entries(roi).map(([family, data]) => {
        const attempts = data.attempts || 0;
        const entities = data.entities || 0;
        const rate = attempts > 0 ? ((entities / attempts) * 100).toFixed(0) : '0';
        return `<div class="roi-card">
            <div class="roi-card-title">${family}</div>
            <div class="roi-card-row"><span class="label">Attempts</span><span class="value">${attempts}</span></div>
            <div class="roi-card-row"><span class="label">Entities</span><span class="value">${entities}</span></div>
            <div class="roi-card-row"><span class="label">Yield</span><span class="value">${rate}%</span></div>
        </div>`;
    }).join('') || '<p class="empty-state">No ROI data.</p>';

    // Domains
    const domainIcons = { Dashboard: '📊', Entities: '🏢', Investments: '📈', Partners: '🤝', Tax: '📋', 'Visual Accounting': '🗺️', 'Data Warehouse': '🗄️', 'Fund Forecasting': '🔮', 'Add Ons': '🧩' };
    document.getElementById('domainsWrap').innerHTML = domains.map(d => {
        const name = (d.name || '').replace(/\n.*/g, '');
        const icon = domainIcons[name] || '📁';
        return `<div class="domain-pill"><span class="icon">${icon}</span>${name}</div>`;
    }).join('') || '<p class="empty-state">No domain data.</p>';
}

// ─── Relationships ───
function renderRelationships() {
    const rels = DATA.fund_relationships || [];
    document.getElementById('relationshipsCount').textContent = rels.length;
    if (rels.length === 0) {
        document.getElementById('noRelsMsg').style.display = 'block';
        return;
    }
    const tbody = document.querySelector('#relationshipsTable tbody');
    tbody.innerHTML = rels.map(r => {
        const dirLabel = (r.direction || '').replace(/_/g, ' ');
        const typeClass = getBadgeClass(r.entity_type);
        return `<tr>
            <td><strong>${r.entity || '—'}</strong></td>
            <td><span class="type-badge ${typeClass}">${r.entity_type || '—'}</span></td>
            <td>${dirLabel || '—'}</td>
            <td><strong>${r.related_fund || '—'}</strong></td>
        </tr>`;
    }).join('');
}

// ─── Agent Testing & Observability ───
function renderTesting() {
    const valRuns = DATA.validation_runs || [];
    const replayMetrics = DATA.replay_metrics || [];
    const crawlRuns = DATA.crawl_runs || [];

    // --- Subtab 1: Validation Runs ---
    const latestRun = valRuns[valRuns.length - 1] || null;
    const latestDetailsDiv = document.getElementById('latestRunDetails');
    const milestoneChecklistDiv = document.getElementById('milestonesChecklist');

    if (latestRun) {
        const totalMilestones = Object.keys(latestRun.milestone_results || {}).length;
        const passedMilestones = Object.values(latestRun.milestone_results || {}).filter(Boolean).length;
        const allPassed = passedMilestones === totalMilestones;
        const statusBadgeClass = allPassed ? 'pass' : 'fail';
        const statusLabel = allPassed ? 'PASSED' : 'FAILED';
        
        latestDetailsDiv.innerHTML = `
            <div style="display:flex; flex-direction:column; gap:0.5rem; justify-content:center; height:100%;">
                <div style="font-size:0.85rem; color:var(--text-secondary)">RUN ID</div>
                <div style="font-family:monospace; font-size:0.9rem; color:var(--text-primary); margin-bottom:0.5rem;">${latestRun.validation_run_id}</div>
                <div style="font-size:0.85rem; color:var(--text-secondary)">COMPLETED AT</div>
                <div style="font-size:0.95rem; font-weight:600; color:var(--text-primary); margin-bottom:0.5rem;">${new Date(latestRun.completed_at).toLocaleString()}</div>
                <div style="font-size:0.85rem; color:var(--text-secondary); margin-bottom:0.25rem;">INTEGRITY RESULT</div>
                <div><span class="status-badge ${statusBadgeClass}">${statusLabel}</span> (${passedMilestones}/${totalMilestones} Milestones)</div>
            </div>
        `;

        milestoneChecklistDiv.innerHTML = Object.entries(latestRun.milestone_results || {}).map(([name, passed]) => {
            const passedClass = passed ? 'passed' : 'failed';
            const statusText = passed ? '✓ Verified' : '✗ Failed';
            return `
                <div class="milestone-item ${passedClass}">
                    <span class="name">${name}</span>
                    <span class="status">${statusText}</span>
                </div>
            `;
        }).join('');
    } else {
        latestDetailsDiv.innerHTML = '<p class="empty-state">No validation run data.</p>';
        milestoneChecklistDiv.innerHTML = '<p class="empty-state">No milestones data.</p>';
    }

    const runsTableBody = document.querySelector('#runsTable tbody');
    if (valRuns.length > 0) {
        runsTableBody.innerHTML = [...valRuns].reverse().map(run => {
            const total = Object.keys(run.milestone_results || {}).length;
            const passed = Object.values(run.milestone_results || {}).filter(Boolean).length;
            const allPassed = passed === total;
            const statusLabel = allPassed ? 'Pass' : 'Fail';
            const badgeCls = allPassed ? 'pass' : 'fail';
            const failuresStr = (run.failures || []).join(', ') || 'None';
            return `
                <tr>
                    <td class="cell-mono">${run.validation_run_id.substring(0, 8)}…</td>
                    <td>${new Date(run.completed_at).toLocaleString()}</td>
                    <td><span style="font-weight:600;">${passed}/${total}</span> milestones</td>
                    <td class="cell-muted" title="${failuresStr}">${failuresStr.substring(0, 30)}${failuresStr.length > 30 ? '…' : ''}</td>
                    <td><span class="status-badge ${badgeCls}">${statusLabel}</span></td>
                </tr>
            `;
        }).join('');
    } else {
        runsTableBody.innerHTML = `<tr><td colspan="5" class="empty-state">No validation run logs available.</td></tr>`;
    }

    // --- Subtab 2: Latency & Performance ---
    const latencyKpiRow = document.getElementById('latencyKpiRow');
    if (latestRun && latestRun.replay_metrics) {
        const metrics = latestRun.replay_metrics;
        const latencyKpis = [
            { v: metrics.auth_extraction_latency_ms.toFixed(3) + 'ms', l: 'Auth Extraction', c: 'var(--accent-emerald)' },
            { v: (metrics.httpx_latency_p50 / 1000).toFixed(2) + 's', l: 'HTTPX p50 Latency', c: 'var(--accent-blue)' },
            { v: (metrics.httpx_latency_p95 / 1000).toFixed(2) + 's', l: 'HTTPX p95 Latency', c: 'var(--accent-amber)' },
            { v: (metrics.api_context_latency_ms / 1000).toFixed(2) + 's', l: 'APIRequestContext', c: 'var(--accent-cyan)' },
            { v: (metrics.browser_fetch_latency_ms / 1000).toFixed(2) + 's', l: 'Browser Fetch', c: 'var(--accent-violet)' },
            { v: (metrics.session_refresh_latency_ms / 1000).toFixed(2) + 's', l: 'Session Refresh', c: 'var(--accent-rose)' },
        ];
        latencyKpiRow.innerHTML = latencyKpis.map(k => `
            <div class="kpi-card">
                <div class="kpi-value" style="color:${k.c}">${k.v}</div>
                <div class="kpi-label">${k.l}</div>
            </div>
        `).join('');
    } else {
        latencyKpiRow.innerHTML = '<div class="kpi-card" style="grid-column: 1/-1;"><p class="empty-state">No latency metrics available.</p></div>';
    }

    const crawlHistoryDiv = document.getElementById('crawlRunsHistory');
    if (crawlRuns.length > 0) {
        crawlHistoryDiv.innerHTML = crawlRuns.map(run => {
            const timeStr = new Date(run.timestamp).toLocaleString();
            const badgeCls = run.success ? 'pass' : 'fail';
            const statusLabel = run.success ? 'Success' : 'Failed';
            const duration = run.performance_profile?.total_duration_sec ? Math.round(run.performance_profile.total_duration_sec) + 's' : '—';
            return `
                <div style="background:var(--bg-table-row); border:1px solid var(--border); border-radius:var(--radius-sm); padding:0.75rem 1rem; display:flex; justify-content:space-between; align-items:center; margin-bottom: 0.5rem;">
                    <div>
                        <div style="font-weight:600; font-size:0.88rem; color:var(--text-primary); margin-bottom:0.2rem;">${run.run_id}</div>
                        <div style="font-size:0.75rem; color:var(--text-muted);">${timeStr}</div>
                    </div>
                    <div style="display:flex; align-items:center; gap:1rem;">
                        <div style="font-size:0.8rem; text-align:right;">
                            <div style="font-weight:600; color:var(--text-primary);">${run.file_count} files</div>
                            <div style="color:var(--text-muted); font-size:0.75rem;">duration: ${duration}</div>
                        </div>
                        <span class="status-badge ${badgeCls}">${statusLabel}</span>
                    </div>
                </div>
            `;
        }).join('');
    } else {
        crawlHistoryDiv.innerHTML = '<p class="empty-state">No historical crawl run telemetry.</p>';
    }

    const latencyBreakdownDiv = document.getElementById('apiLatencyBreakdown');
    if (latestRun && latestRun.replay_metrics) {
        const metrics = latestRun.replay_metrics;
        const items = [
            { name: 'Auth Extraction', val: metrics.auth_extraction_latency_ms, unit: 'ms', color: 'var(--accent-emerald)' },
            { name: 'HTTPX p50 Request', val: metrics.httpx_latency_p50, unit: 'ms', color: 'var(--accent-blue)' },
            { name: 'HTTPX p95 Request', val: metrics.httpx_latency_p95, unit: 'ms', color: 'var(--accent-amber)' },
            { name: 'APIRequestContext', val: metrics.api_context_latency_ms, unit: 'ms', color: 'var(--accent-cyan)' },
            { name: 'Browser Fetch', val: metrics.browser_fetch_latency_ms, unit: 'ms', color: 'var(--accent-violet)' },
            { name: 'Session Refresh', val: metrics.session_refresh_latency_ms, unit: 'ms', color: 'var(--accent-rose)' },
        ];
        const maxVal = Math.max(...items.map(i => i.val), 1);
        latencyBreakdownDiv.innerHTML = `
            <div style="display:flex; flex-direction:column; gap:0.85rem; padding:0.5rem 0;">
                ${items.map(item => {
                    const pct = Math.max((item.val / maxVal) * 100, 2);
                    const valText = item.unit === 'ms' && item.val >= 1000 ? (item.val / 1000).toFixed(2) + 's' : item.val.toFixed(0) + item.unit;
                    return `
                        <div>
                            <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:0.25rem;">
                                <span style="color:var(--text-secondary); font-weight:500;">${item.name}</span>
                                <span style="color:var(--text-primary); font-weight:600;">${valText}</span>
                            </div>
                            <div style="height:10px; background:var(--bg-table-row); border-radius:4px; overflow:hidden;">
                                <div style="height:100%; width:${pct}%; background:${item.color}; border-radius:4px; transition:width 0.6s ease;"></div>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    } else {
        latencyBreakdownDiv.innerHTML = '<p class="empty-state">No latency breakdown data.</p>';
    }

    // --- Subtab 3: Data Coverage Audit ---
    const gapsTableBody = document.querySelector('#gapsTable tbody');
    const schemaMapping = [
        { table: 'companies', page: 'Direct / Fund Investments', source: 'company_profiles / list_firm_investments', status: 'full', action: 'Directly mapped from Carta extraction' },
        { table: 'funding_rounds', page: 'Investments detail', source: 'valuations / post_money / funds_raised', status: 'full', action: 'Directly mapped from Carta valuations' },
        { table: 'cap_tables', page: 'Cap Table snapshot', source: 'cap_tables / stakeholder list', status: 'full', action: 'Mapped from stakeholder ownership' },
        { table: 'stakeholders', page: 'Cap Table & Investors', source: 'cap_tables.stakeholder / investors list', status: 'full', action: 'Mapped from cap table stakeholder registry' },
        { table: 'transactions', page: 'Investments detail / History', source: 'irr_performance.transactions', status: 'full', action: 'Mapped from transaction ledger extraction' },
        { table: 'valuations', page: 'Portfolio & SPV Dashboards', source: 'fmv_409a / post_money', status: 'full', action: 'Directly mapped from Carta valuations' },
        { table: 'securities', page: 'Securities detail', source: 'securities (classes, shares, cost)', status: 'full', action: 'Mapped from share classes / certificates' },
        { table: 'contacts', page: 'Contacts list', source: 'contacts (email, role, primary)', status: 'full', action: 'Directly mapped from firm members / portfolio contacts' },
        { table: 'documents', page: 'Documents vault', source: 'documents (name, url, category)', status: 'full', action: 'Mapped from document extraction library' },
        { table: 'investments', page: 'Investments catalog', source: 'list_firm_investments', status: 'full', action: 'Directly mapped from investments list' },
        { table: 'funds', page: 'Fund Overview', source: 'funds / fund_structure', status: 'full', action: 'Mapped from fund permission groups' },
        { table: 'spvs', page: 'SPV Overview / Metrics', source: 'spvs / fund_structure', status: 'full', action: 'Mapped from SPV permission groups' },
        { table: 'expenses', page: 'SPV Overview', source: 'External Source (Bank feeds/accounting)', status: 'stub', action: 'Needs QuickBooks or manual invoices integration' },
        { table: 'interest_allocations', page: 'SPV Structure', source: 'External Source (Bank feeds)', status: 'stub', action: 'Needs Plaid/Stripe bank feed integration' },
        { table: 'management_fees', page: 'SPV Overview / Fund Overview', source: 'Partial (Carta stubs)', status: 'partial', action: 'Requires parsing management fee schedules in PDF' },
        { table: 'partner_capital_accounts', page: 'SPV Structure', source: 'Partial (Carta document ledger)', status: 'partial', action: 'Requires capital account statement PDF parser' },
        { table: 'growing_traction', page: 'Fund / SPV Metrics', source: 'External Source (PitchBook/CRM)', status: 'stub', action: 'Needs PitchBook/Crunchbase API integration' },
        { table: 'sector_classifications', page: 'Fund / SPV Overview', source: 'External Source (PitchBook API)', status: 'stub', action: 'Needs PitchBook classification lookup' },
        { table: 'company_news', page: 'Direct Overview', source: 'External Source (News API)', status: 'stub', action: 'Needs Google News or Bing News API parser integration' }
    ];

    gapsTableBody.innerHTML = schemaMapping.map(row => {
        return `
            <tr>
                <td><strong>${row.table}</strong></td>
                <td style="color:var(--text-secondary);">${row.page}</td>
                <td class="cell-mono" style="font-size:0.8rem;">${row.source}</td>
                <td><span class="coverage-status ${row.status}">${row.status.toUpperCase()}</span></td>
                <td style="font-size:0.82rem; color:var(--text-secondary);">${row.action}</td>
            </tr>
        `;
    }).join('');
}

// ─── Platform API Explorer ───
const platformEndpoints = [
    { name: 'get_investments', table: 'inv_investment', desc: 'Returns all investments, mapping the PortfolioCompany and Holding canonical entities into the core platform asset registry.' },
    { name: 'get_investment_extra_info', table: 'inv_asset_extra_info', desc: 'Returns qualitative research information like investment thesis and tailwinds.' },
    { name: 'get_investment_team', table: 'inv_asset_team', desc: 'Returns key people, founders, and contacts associated with the investment.' },
    { name: 'get_investment_valuations', table: 'inv_asset_valuation', desc: 'Returns historical valuations (e.g., 409A and Post-Money).' },
    { name: 'get_capital_calls', table: 'inv_cap_call', desc: 'Returns debit transactions classified as capital calls against an investment.' },
    { name: 'get_investment_log', table: 'investment_log', desc: 'Returns point-in-time value snapshots tracking cumulative investment amounts over time.' },
    { name: 'get_investment_transactions', table: 'inv_investment_transaction', desc: 'Returns all inflow and outflow transactions associated with an investment.' },
    { name: 'get_documents', table: 'inv_investment_document', desc: 'Returns files, documents, and updates associated with the investments.' },
    { name: 'get_partner_metrics', table: 'partner_metrics', desc: 'Returns partner performance metrics (commitment, net asset value, distributions, vintage year, etc.) for LP interests.' },
    { name: 'get_investment_firm', table: 'inv_investment_firm', desc: 'Returns the GP/firm profile including AUM and active funds.' },
    { name: 'get_investment_focus', table: 'inv_investment_focus', desc: 'Returns portfolio focus overview, current year valuation, and Multiple on Invested Capital (MOIC).' },
    { name: 'get_investment_sectors', table: 'inv_investment_sector', desc: 'Returns sector and stage classification of the investments.' },
    { name: 'get_investment_certificates', table: 'inv_investment_certificate', desc: 'Returns share certificates, issue dates, and certificate status.' },
    { name: 'get_distribution_history', table: 'inv_investment_distribution_history', desc: 'Returns credit transactions classified as distribution events.' },
    { name: 'get_liquidity_distributions', table: 'inv_liquidity_distribution', desc: 'Returns detailed liquidity event distributions and their sources.' },
    { name: 'get_investment_expenses', table: 'inv_investment_expense', desc: 'Returns categorized expenses associated with the investment.' },
    { name: 'get_investment_interest', table: 'inv_investment_interest', desc: 'Returns interest earnings on the investment.' },
    { name: 'get_investment_services', table: 'inv_investment_service', desc: 'Returns service records and associated vendor costs.' },
    { name: 'get_usage_logs', table: 'inv_asset_usage_log', desc: 'Returns usage logs for physical assets (empty for Venture).' },
    { name: 'get_recent_developments', table: 'extra_info_recent_development', desc: 'Returns tracked news and recent developments.' },
    { name: 'get_growth_signals', table: 'research_growing_traction', desc: 'Returns extracted traction and growth signals.' },
    { name: 'get_capital_account_summary', table: 'partner_capital_account_summary', desc: 'Returns the partner capital account summary and transactions within the specified date range.' },
    { name: 'get_coverage', table: 'coverage_matrix', desc: 'Exposes a real-time field population coverage matrix.' }
];

let currentSyncTaskId = null;
let syncPollInterval = null;

function setupPlatformApiExplorer() {
    const endpointSelect = document.getElementById('apiEndpointSelect');
    if (!endpointSelect) return;

    const customEndpointGroup = document.getElementById('customEndpointGroup');
    const customInput = document.getElementById('apiCustomEndpoint');

    // Handle selection change
    endpointSelect.addEventListener('change', () => {
        if (endpointSelect.value === 'custom') {
            if (customEndpointGroup) customEndpointGroup.style.display = 'flex';
        } else {
            if (customEndpointGroup) customEndpointGroup.style.display = 'none';
        }
        updateInspectorHeader();
    });

    if (customInput) {
        customInput.addEventListener('input', updateInspectorHeader);
    }

    // Setup Explorer Tabs (UI Preview vs JSON Source)
    const btnUiView = document.getElementById('btnPlatformUiView');
    const btnJsonView = document.getElementById('btnPlatformJsonView');
    const uiViewContainer = document.getElementById('platformUiViewContainer');
    const jsonPre = document.getElementById('platformJsonPre');

    if (btnUiView && btnJsonView) {
        btnUiView.addEventListener('click', () => {
            activeExplorerTab = 'ui';
            btnUiView.classList.add('active');
            btnJsonView.classList.remove('active');
            if (uiViewContainer) uiViewContainer.style.display = 'block';
            if (jsonPre) jsonPre.style.display = 'none';
        });
        btnJsonView.addEventListener('click', () => {
            activeExplorerTab = 'json';
            btnJsonView.classList.add('active');
            btnUiView.classList.remove('active');
            if (jsonPre) jsonPre.style.display = 'block';
            if (uiViewContainer) uiViewContainer.style.display = 'none';
        });
    }

    // Handle Copy button
    document.getElementById('btnCopyToClipboard').addEventListener('click', () => {
        const pre = document.getElementById('platformJsonPre');
        if (pre && pre.textContent) {
            navigator.clipboard.writeText(pre.textContent)
                .then(() => {
                    const btn = document.getElementById('btnCopyToClipboard');
                    const origText = btn.textContent;
                    btn.textContent = 'Copied!';
                    btn.style.background = 'var(--accent-emerald)';
                    btn.style.color = '#000';
                    setTimeout(() => {
                        btn.textContent = origText;
                        btn.style.background = '';
                        btn.style.color = '';
                    }, 1500);
                })
                .catch(err => console.error('Failed to copy text: ', err));
        }
    });

    // Handle Send Button click
    const btnSend = document.getElementById('btnSendApiRequest');
    if (btnSend) {
        btnSend.addEventListener('click', () => {
            sendApiRequest();
        });
    }

    // Initialize inspector view
    updateInspectorHeader();
}

function updateInspectorHeader() {
    const endpointSelect = document.getElementById('apiEndpointSelect');
    if (!endpointSelect) return;

    let endpointName = endpointSelect.value;
    if (endpointName === 'custom') {
        const customInput = document.getElementById('apiCustomEndpoint');
        endpointName = (customInput && customInput.value.trim()) ? customInput.value.trim() : 'custom_endpoint';
    }

    const ep = platformEndpoints.find(e => e.name === endpointName);

    document.getElementById('inspectorEndpointName').textContent = endpointName;
    document.getElementById('inspectorTableName').textContent = ep ? ep.table : 'custom_result';
    document.getElementById('inspectorDescription').textContent = ep ? ep.desc : 'Configure details on the left, then click Send Request to query.';
}

async function sendApiRequest() {
    const pre = document.getElementById('platformJsonPre');
    const uiContainer = document.getElementById('platformUiViewContainer');
    if (!pre) return;

    const endpointSelect = document.getElementById('apiEndpointSelect');
    if (!endpointSelect) return;
    let endpointName = endpointSelect.value;
    if (endpointName === 'custom') {
        const customInput = document.getElementById('apiCustomEndpoint');
        endpointName = (customInput && customInput.value.trim()) ? customInput.value.trim() : '';
    }

    if (!endpointName) {
        alert("Please enter a custom endpoint name.");
        return;
    }

    pre.textContent = `Sending POST request to /api/sync-endpoint for ${endpointName}...`;
    if (uiContainer) {
        uiContainer.innerHTML = '<div style="color:var(--accent-violet); padding: 2rem; text-align: center;">Sending request...</div>';
    }

    const btn = document.getElementById('btnSendApiRequest');
    let originalBtnHtml = "";
    if (btn) {
        originalBtnHtml = btn.innerHTML;
        btn.innerHTML = '<span>⏳</span> <span>Sending...</span>';
        btn.disabled = true;
        btn.style.opacity = '0.7';
    }

    // Build API payload
    const payload = { endpoint: endpointName };

    const firmIdVal = document.getElementById('apiFirmId').value.trim();
    if (firmIdVal) payload.firm_id = parseInt(firmIdVal, 10);

    const entityIdVal = document.getElementById('apiEntityId').value.trim();
    if (entityIdVal) payload.entity_id = parseInt(entityIdVal, 10);

    const orgIdVal = document.getElementById('apiOrgId').value.trim();
    if (orgIdVal) payload.org_id = parseInt(orgIdVal, 10);

    const orgUuidVal = document.getElementById('apiOrgUuid').value.trim();
    if (orgUuidVal) payload.org_uuid = orgUuidVal;

    const fundUuidVal = document.getElementById('apiFundUuid').value.trim();
    if (fundUuidVal) payload.fund_uuid = fundUuidVal;

    const partnerIdVal = document.getElementById('apiPartnerId').value.trim();
    if (partnerIdVal) payload.partner_id = partnerIdVal;

    const startDateVal = document.getElementById('apiStartDate').value.trim();
    if (startDateVal) payload.start_date = startDateVal;

    const endDateVal = document.getElementById('apiEndDate').value.trim();
    if (endDateVal) payload.end_date = endDateVal;

    try {
        const res = await fetch('/api/sync-endpoint', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail?.error || `HTTP error ${res.status}`);
        }

        const resultData = await res.json();

        // Reload dashboard data dynamically in background
        fetch('data/business_data.json').then(async (reloadRes) => {
            if (reloadRes.ok) {
                DATA = await reloadRes.json();
                renderSidebar();
                renderOverview();
                renderFunds();
                renderSPVs();
                renderInvestments();
                renderInvestors();
                renderDocuments();
                renderExports();
                renderEntityGraph();
                renderPipeline();
                renderRelationships();
                renderTesting();
            }
        }).catch(err => console.error("Failed to reload background data:", err));

        // Render json output
        pre.textContent = JSON.stringify(resultData, null, 2);
        if (uiContainer) {
            renderUiPreviewWithStatus(endpointName, resultData, uiContainer);
        }

        if (btn) {
            btn.innerHTML = '<span>✅</span> <span>Sent Successfully</span>';
            btn.style.background = 'rgba(16, 185, 129, 0.15)';
            btn.style.color = '#34d399';
            setTimeout(() => {
                btn.innerHTML = originalBtnHtml;
                btn.style.background = '';
                btn.style.color = '';
                btn.disabled = false;
                btn.style.opacity = '';
            }, 2000);
        }

    } catch (err) {
        pre.textContent = `Request failed:\n\n${err.message}\n\nPlease check server logs.`;
        if (uiContainer) {
            uiContainer.innerHTML = `<div style="color:var(--accent-rose); padding: 2rem; text-align: center;">Request failed: ${err.message}</div>`;
        }
        if (btn) {
            btn.innerHTML = '<span>❌</span> <span>Failed</span>';
            btn.style.background = 'rgba(239, 68, 68, 0.15)';
            btn.style.color = '#f87171';
            setTimeout(() => {
                btn.innerHTML = originalBtnHtml;
                btn.style.background = '';
                btn.style.color = '';
                btn.disabled = false;
                btn.style.opacity = '';
            }, 2000);
        }
    }
}

function renderUiPreviewWithStatus(endpointName, resultData, container) {
    if (!container) return;
    
    container.innerHTML = '';
    
    const isSuccess = resultData.status_code === 200;
    const banner = document.createElement('div');
    banner.style.cssText = `
        background: ${isSuccess ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)'};
        border: 1px solid ${isSuccess ? 'var(--accent-emerald)' : 'var(--accent-rose)'};
        border-radius: var(--radius-sm);
        padding: 0.75rem;
        margin-bottom: 1rem;
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        font-size: 0.85rem;
    `;
    
    banner.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 600; color: ${isSuccess ? 'var(--accent-emerald)' : 'var(--accent-rose)'};">
                ${isSuccess ? '🟢 Sync Successful (200 OK)' : `🔴 Sync Failed (${resultData.status_code})`}
            </span>
            <span style="color: var(--text-muted); font-family: monospace;">Latency: ${resultData.latency_ms || 0}ms</span>
        </div>
        <div style="font-size: 0.75rem; color: var(--text-secondary); word-break: break-all; font-family: monospace;">
            <strong>URL:</strong> ${resultData.url || 'N/A'}
        </div>
    `;
    container.appendChild(banner);
    
    const contentDiv = document.createElement('div');
    container.appendChild(contentDiv);
    
    renderUiPreview(endpointName, resultData, contentDiv);
}

/* ─── Platform Explorer UI Previews ─── */
function renderUiPreview(endpointName, responseData, container) {
    if (!container) return;

    if (endpointName === 'get_coverage') {
        renderCoverageUi(responseData, container);
        return;
    }

    let records = responseData.data || [];
    if (records && typeof records === 'object' && !Array.isArray(records)) {
        if (Array.isArray(records.results)) {
            records = records.results;
        } else {
            records = [records];
        }
    }
    if (!Array.isArray(records) || records.length === 0) {
        container.innerHTML = `
            <div style="padding: 3rem 1.5rem; text-align: center; border: 1px dashed var(--border); border-radius: var(--radius-sm); background: rgba(255,255,255,0.01);">
                <div style="font-size: 2rem; margin-bottom: 0.75rem;">📁</div>
                <div style="font-weight: 600; font-size: 0.95rem; color: var(--text-primary); margin-bottom: 0.25rem;">No Records Captured</div>
                <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.4; max-width: 320px; margin: 0 auto;">
                    This endpoint represents the <code>${responseData.table || 'unknown'}</code> table. Run full extraction or sync this endpoint to load live data.
                </p>
            </div>
        `;
        return;
    }

    switch (endpointName) {
        case 'get_investments':
            renderInvestmentsUi(records, container);
            break;
        case 'get_investment_extra_info':
            renderExtraInfoUi(records, container);
            break;
        case 'get_investment_team':
            renderTeamUi(records, container);
            break;
        case 'get_investment_valuations':
            renderValuationsUi(records, container);
            break;
        case 'get_capital_calls':
            renderCapitalCallsUi(records, container);
            break;
        case 'get_investment_log':
            renderInvestmentLogUi(records, container);
            break;
        case 'get_investment_transactions':
            renderTransactionsUi(records, container);
            break;
        case 'get_investment_certificates':
            renderCertificatesUi(records, container);
            break;
        case 'get_distribution_history':
            renderDistributionsUi(records, container);
            break;
        case 'get_capital_account_summary':
            renderCapitalAccountSummaryUi(records, container);
            break;
        case 'get_partner_metrics':
            renderPartnerMetricsUi(records, container);
            break;
        default: {
            const ep = platformEndpoints.find(e => e.name === endpointName);
            const tableName = ep ? ep.table : (responseData.table || 'custom_result');
            renderDefaultTableUi(tableName, records, container);
            break;
        }
    }
}

function renderInvestmentsUi(records, container) {
    let html = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Company / Asset</th>
                    <th>Category</th>
                    <th>Held Since</th>
                    <th style="text-align:right;">Capital Invested</th>
                    <th style="text-align:right;">Current Value</th>
                    <th style="text-align:right;">Gain / Loss</th>
                    <th style="text-align:right;">Ownership %</th>
                    <th style="text-align:right;">Multiple</th>
                    <th style="text-align:right;">IRR</th>
                </tr>
            </thead>
            <tbody>
    `;

    records.forEach(r => {
        const cost = r.investment_amount;
        const val = r.valuation;
        const gainLoss = (val && cost) ? (val - cost) : null;
        const multiple = (val && cost && cost > 0) ? (val / cost) : null;
        const irr = r.irr;

        html += `
            <tr>
                <td><strong>${r.asset_name || r.asset_id}</strong></td>
                <td><span class="type-badge fund">${r.asset_category || 'Venture'}</span></td>
                <td class="cell-muted">${r.investment_date || '—'}</td>
                <td style="text-align:right; font-weight:600;">${cost ? formatMoney(cost) : '—'}</td>
                <td style="text-align:right; font-weight:600; color:var(--text-accent);">${val ? formatMoney(val) : '—'}</td>
                <td style="text-align:right; font-weight:600; color:${gainLoss >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)'};">
                    ${gainLoss !== null ? (gainLoss >= 0 ? '+' : '') + formatMoney(gainLoss) : '—'}
                </td>
                <td style="text-align:right; font-family:monospace; color:var(--text-secondary);">${r.ownership_percentage ? r.ownership_percentage.toFixed(2) + '%' : '—'}</td>
                <td style="text-align:right; font-weight:600; color:var(--accent-amber);">${multiple ? multiple.toFixed(2) + 'x' : '—'}</td>
                <td style="text-align:right; font-weight:600; color:var(--accent-violet);">${irr ? irr.toFixed(1) + '%' : '—'}</td>
            </tr>
        `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
}

function renderExtraInfoUi(records, container) {
    let html = `<div class="explorer-grid-cards">`;
    records.forEach(r => {
        html += `
            <div class="explorer-info-card" style="grid-column: 1 / -1;">
                <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding-bottom:0.5rem; margin-bottom:0.5rem;">
                    <div class="explorer-info-title">Asset Research Profile: ${r.investment_id}</div>
                    ${r.website ? `<a href="${r.website}" target="_blank" style="font-size:0.75rem; color:var(--accent-blue); text-decoration:none;">🌐 Visit Website</a>` : ''}
                </div>
                <div style="display:flex; flex-direction:column; gap:0.75rem;">
                    <div>
                        <div style="font-size:0.7rem; color:var(--text-muted); text-transform:uppercase; margin-bottom:0.25rem;">Industry Overview</div>
                        <p style="font-size:0.85rem; line-height:1.4; color:var(--text-primary);">${r.industry_overview || 'No industry overview populated.'}</p>
                    </div>
                    <div>
                        <div style="font-size:0.7rem; color:var(--text-muted); text-transform:uppercase; margin-bottom:0.25rem;">Investment Thesis</div>
                        <p style="font-size:0.85rem; line-height:1.4; color:var(--text-secondary); font-style:italic;">"${r.investment_thesis || 'No investment thesis provided.'}"</p>
                    </div>
                    <div>
                        <div style="font-size:0.7rem; color:var(--text-muted); text-transform:uppercase; margin-bottom:0.25rem;">Industry Competitors</div>
                        <p style="font-size:0.85rem; line-height:1.4; color:var(--text-secondary);">${r.industry_competitors || 'No competitors listed.'}</p>
                    </div>
                </div>
            </div>
        `;
    });
    html += `</div>`;
    container.innerHTML = html;
}

function renderTeamUi(records, container) {
    let html = `<div class="explorer-grid-cards">`;
    records.forEach(r => {
        const initials = ((r.first_name || '').substring(0, 1) + (r.last_name || '').substring(0, 1)).toUpperCase() || '?';
        html += `
            <div class="explorer-profile-card">
                <div class="explorer-profile-avatar">${initials}</div>
                <div class="explorer-profile-details">
                    <div class="explorer-profile-name">${r.first_name || ''} ${r.last_name || ''}</div>
                    <div class="explorer-profile-designation">${r.designation || 'Team Member'}</div>
                    ${r.email ? `<a href="mailto:${r.email}" class="explorer-profile-email">${r.email}</a>` : ''}
                    <div style="font-size:0.65rem; color:var(--text-muted); margin-top:0.25rem;">Asset ID: ${r.investment_id}</div>
                </div>
            </div>
        `;
    });
    html += `</div>`;
    container.innerHTML = html;
}

function renderValuationsUi(records, container) {
    if (!Array.isArray(records)) {
        records = [records];
    }
    const firstRec = records[0];
    if (!firstRec) return;

    // Check if it's the raw API explorer payload
    const isRaw = firstRec.tabs !== undefined || firstRec.holdings !== undefined || firstRec.normalized_fund_metrics !== undefined;

    if (!isRaw) {
        // Fallback to standard canonical valuations list
        let html = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Asset / Investment ID</th>
                        <th>Valuation Date</th>
                        <th style="text-align:right;">Valuation Amount</th>
                        <th>Fiscal Year</th>
                    </tr>
                </thead>
                <tbody>
        `;

        records.forEach(r => {
            html += `
                <tr>
                    <td><strong>${r.investment_id || '—'}</strong></td>
                    <td>${r.date || '—'}</td>
                    <td style="text-align:right; font-weight:600; color:var(--accent-emerald);">${r.amount ? formatMoney(r.amount) : '—'}</td>
                    <td style="font-family:monospace; color:var(--text-secondary);">${r.year || '—'}</td>
                </tr>
            `;
        });

        html += `</tbody></table>`;
        container.innerHTML = html;
        return;
    }

    // It's the raw API explorer payload!
    const metrics = firstRec.normalized_fund_metrics || {};
    const holdings = firstRec.holdings || {};
    const valuations = firstRec.valuations || {};
    const ledger = firstRec.ledger || {};
    
    // Extract holding row details
    let holdingRow = null;
    if (holdings && Array.isArray(holdings.rows) && holdings.rows.length > 0) {
        holdingRow = holdings.rows[0];
    }

    // Safe division helper (values in holdings.rows are in cents)
    const formatCents = (centsVal) => {
        if (centsVal === null || centsVal === undefined) return '—';
        return formatMoney(parseFloat(centsVal) / 100.0);
    };

    const fundName = metrics.fund_name || (holdingRow ? holdingRow.fund_name : 'Unknown Fund');
    const heldSince = metrics.held_since || (holdingRow ? holdingRow.vintage_year : '—');
    const netAssetValueUsd = metrics.net_asset_value_usd !== undefined ? metrics.net_asset_value_usd : (holdingRow ? holdingRow.net_asset_value / 100 : null);
    const cashCostUsd = metrics.cash_cost_usd !== undefined ? metrics.cash_cost_usd : (holdingRow ? holdingRow.contributed / 100 : null);
    const multiple = metrics.multiple !== undefined ? metrics.multiple : ((netAssetValueUsd && cashCostUsd) ? (netAssetValueUsd / cashCostUsd) : null);
    const currency = metrics.currency || (holdingRow ? holdingRow.fund_currency : 'USD');

    let moicColor = 'var(--text-secondary)';
    if (multiple !== null) {
        moicColor = multiple >= 1.0 ? 'var(--accent-emerald)' : 'var(--accent-rose)';
    }

    let html = `
        <!-- Dashboard Profile Header -->
        <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 1.25rem; margin-bottom: 1.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <span style="font-size: 0.75rem; text-transform: uppercase; color: var(--accent-cyan); font-weight: 600; letter-spacing: 0.05em;">Valuation & Holdings Profile</span>
                    <h3 style="margin: 0.25rem 0 0.5rem 0; font-size: 1.3rem; color: var(--text-primary);">${fundName}</h3>
                    <div style="display: flex; gap: 1.5rem; flex-wrap: wrap; font-size: 0.82rem; color: var(--text-secondary);">
                        <div><strong>Vintage Year:</strong> ${heldSince}</div>
                        <div><strong>Reporting Currency:</strong> ${currency}</div>
                        ${holdingRow && holdingRow.primary_contact_email ? `<div><strong>Contact:</strong> ${holdingRow.primary_contact_email}</div>` : ''}
                    </div>
                </div>
                <div style="text-align: right; font-size: 0.82rem; color: var(--text-secondary);">
                    <div><strong>As of Sharing Date:</strong> ${holdingRow && holdingRow.lp_sharing_date ? holdingRow.lp_sharing_date : '—'}</div>
                </div>
            </div>
        </div>

        <!-- Valuation Financial Cards -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
            <div style="background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: var(--radius-sm); padding: 1.25rem;">
                <div style="font-size: 0.7rem; color: var(--accent-emerald); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Net Asset Value (NAV)</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: var(--accent-emerald); font-family: monospace;">${netAssetValueUsd !== null ? formatMoney(netAssetValueUsd) : '—'}</div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">Estimated Current Value</div>
            </div>

            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 1.25rem;">
                <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Invested Capital (Cost)</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: var(--text-primary); font-family: monospace;">${cashCostUsd !== null ? formatMoney(cashCostUsd) : '—'}</div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">Total Contributed Capital</div>
            </div>

            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 1.25rem; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Multiple (MOIC)</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: ${moicColor}; font-family: monospace;">${multiple !== null ? multiple.toFixed(2) + 'x' : '—'}</div>
                </div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">Value Multiple of Invested Capital</div>
            </div>
        </div>

        <!-- Holdings Details & Commitments Section -->
        ${holdingRow ? `
            <div class="card" style="margin-bottom: 1.5rem;">
                <h4 style="margin: 0 0 1rem 0; font-size: 0.95rem; color: var(--text-primary);">Capital Commitment & Allocation Details</h4>
                <div class="table-wrap">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Commitment Type</th>
                                <th style="text-align: right;">Amount (USD)</th>
                                <th>Status / Notes</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td><strong>Total Commitment</strong></td>
                                <td style="text-align: right; font-weight: 600; font-family: monospace; color: var(--text-primary);">${formatCents(holdingRow.committed)}</td>
                                <td class="cell-muted" style="font-size: 0.8rem;">Initial capital commitment signed with fund.</td>
                            </tr>
                            <tr>
                                <td><strong>Capital Called</strong></td>
                                <td style="text-align: right; font-weight: 600; font-family: monospace; color: var(--text-primary);">${formatCents(holdingRow.capital_called)}</td>
                                <td class="cell-muted" style="font-size: 0.8rem;">Total drawdown requests issued by the GP.</td>
                            </tr>
                            <tr>
                                <td><strong>Contributed Paid</strong></td>
                                <td style="text-align: right; font-weight: 600; font-family: monospace; color: var(--accent-emerald);">${formatCents(holdingRow.contributed_paid)}</td>
                                <td class="cell-muted" style="font-size: 0.8rem;">Cleared portion of contributions.</td>
                            </tr>
                            <tr>
                                <td><strong>Outstanding Liabilities</strong></td>
                                <td style="text-align: right; font-weight: 600; font-family: monospace; color: ${holdingRow.capital_contributed_liabilities > 0 ? 'var(--accent-rose)' : 'var(--text-primary)'};">${formatCents(holdingRow.capital_contributed_liabilities)}</td>
                                <td class="cell-muted" style="font-size: 0.8rem; color: ${holdingRow.capital_contributed_liabilities > 0 ? 'var(--accent-rose)' : 'var(--text-muted)'};">
                                    ${holdingRow.capital_contributed_liabilities > 0 ? '⚠️ Unpaid capital call balance due' : 'Fully paid up.'}
                                </td>
                            </tr>
                            <tr>
                                <td><strong>Prepaid Contributed</strong></td>
                                <td style="text-align: right; font-weight: 600; font-family: monospace; color: var(--text-primary);">${formatCents(holdingRow.prepaid_contributed)}</td>
                                <td class="cell-muted" style="font-size: 0.8rem;">Advance payments credit.</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        ` : ''}

        <!-- Live Endpoint API Status Alerts (403/404 handling) -->
        <div style="display: flex; flex-direction: column; gap: 0.75rem; margin-top: 1rem;">
            ${valuations && valuations.error ? `
                <div style="background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.15); border-radius: var(--radius-sm); padding: 0.85rem; display: flex; justify-content: space-between; align-items: center; font-size: 0.82rem;">
                    <span style="color: var(--text-secondary); display: flex; align-items: center; gap: 0.5rem;">
                        <span style="color: var(--accent-rose);">⚠️</span>
                        <span>Historical 409A Valuations API:</span>
                    </span>
                    <span class="coverage-status gap" style="font-family: monospace; font-size: 0.78rem;">${valuations.error}</span>
                </div>
            ` : ''}

            ${ledger && ledger.error ? `
                <div style="background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.15); border-radius: var(--radius-sm); padding: 0.85rem; display: flex; justify-content: space-between; align-items: center; font-size: 0.82rem;">
                    <span style="color: var(--text-secondary); display: flex; align-items: center; gap: 0.5rem;">
                        <span style="color: var(--accent-rose);">⚠️</span>
                        <span>Statement of Investments (SOI) Ledger API:</span>
                    </span>
                    <span class="coverage-status gap" style="font-family: monospace; font-size: 0.78rem;">${ledger.error}</span>
                </div>
            ` : ''}
        </div>
    `;

    container.innerHTML = html;
}

function renderCapitalCallsUi(records, container) {
    if (records && !Array.isArray(records) && Array.isArray(records.results)) {
        records = records.results;
    }
    if (!Array.isArray(records)) {
        records = [records];
    }

    let html = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Call Date</th>
                    <th>Asset / Investment ID</th>
                    <th>Fund Reference</th>
                    <th style="text-align:right;">Amount</th>
                    <th>Description / Notes</th>
                </tr>
            </thead>
            <tbody>
    `;

    records.forEach(r => {
        const date = r.date || r.transaction_date || '—';
        const investmentId = r.investment_id || r.fund_id || r.portfolio_id || '—';
        const fundName = r.fund_name || 'Active Fund';
        const amount = r.amount !== undefined ? r.amount : null;
        
        let description = r.notes || r.transaction_type || '—';
        if (r.notes && r.transaction_type && r.notes !== r.transaction_type) {
            description = `${r.transaction_type} (${r.notes})`;
        }

        const color = amount < 0 ? 'var(--accent-rose)' : 'var(--accent-emerald)';
        const prefix = amount >= 0 ? '+' : '';

        html += `
            <tr>
                <td>${date}</td>
                <td><strong>${investmentId}</strong></td>
                <td><span class="type-badge spv">${fundName}</span></td>
                <td style="text-align:right; font-weight:600; color:${color};">${amount !== null ? prefix + formatMoney(amount) : '—'}</td>
                <td class="cell-muted" style="font-size:0.8rem;">${description}</td>
            </tr>
        `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
}

function renderInvestmentLogUi(records, container) {
    if (!Array.isArray(records)) {
        records = [records];
    }
    const firstRec = records[0];
    if (!firstRec) return;

    // Check if it's raw transactions payload
    const isRaw = firstRec.transaction_date !== undefined || firstRec.transaction_type !== undefined || firstRec.cash_cents !== undefined;

    if (!isRaw) {
        // Fallback to standard canonical investment log
        let html = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Log Date</th>
                        <th>Asset / Investment ID</th>
                        <th style="text-align:right;">Cumulative Capital Deployed</th>
                    </tr>
                </thead>
                <tbody>
        `;

        records.forEach(r => {
            html += `
                <tr>
                    <td>${r.investment_date || '—'}</td>
                    <td><strong>${r.investment_id || '—'}</strong></td>
                    <td style="text-align:right; font-weight:600; color:var(--accent-emerald); font-family:monospace;">${r.investment_amount ? formatMoney(r.investment_amount) : '—'}</td>
                </tr>
            `;
        });

        html += `</tbody></table>`;
        container.innerHTML = html;
        return;
    }

    // It's the raw transaction log response!
    const parseDate = (dStr) => {
        if (!dStr) return new Date(0);
        const parts = dStr.split('/');
        if (parts.length === 3) {
            return new Date(parseInt(parts[2]), parseInt(parts[0]) - 1, parseInt(parts[1]));
        }
        return new Date(dStr);
    };

    const sortedRaw = [...records].sort((a, b) => parseDate(a.transaction_date) - parseDate(b.transaction_date));

    let cumulative = 0;
    const logEntries = [];

    sortedRaw.forEach(r => {
        const type = (r.transaction_type || '').toLowerCase();
        const isContrib = type.includes('contribution') || type.includes('call') || type.includes('drawdown');

        if (isContrib) {
            const amt = parseFloat(r.amount) || 0;
            cumulative += amt;
            logEntries.push({
                date: r.transaction_date || '—',
                fund: r.fund_name || `Fund #${r.fund_id || '—'}`,
                type: r.transaction_type || 'Contribution',
                amount: amt,
                cumulative: cumulative
            });
        }
    });

    if (logEntries.length === 0) {
        container.innerHTML = `
            <div style="padding: 3rem 1.5rem; text-align: center; border: 1px dashed var(--border); border-radius: var(--radius-sm); background: rgba(255,255,255,0.01);">
                <div style="font-size: 2rem; margin-bottom: 0.75rem;">📈</div>
                <div style="font-weight: 600; font-size: 0.95rem; color: var(--text-primary); margin-bottom: 0.25rem;">No Capital Contributions Found</div>
                <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.4; max-width: 320px; margin: 0 auto;">
                    We scanned the transactions list, but did not find any capital contribution type entries to plot the deployment timeline.
                </p>
            </div>
        `;
        return;
    }

    // Sort descending for display (most recent first)
    const displayEntries = [...logEntries].reverse();

    let html = `
        <!-- Timeline Deployed Summary -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
            <div style="background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: var(--radius-sm); padding: 1.25rem;">
                <div style="font-size: 0.7rem; color: var(--accent-emerald); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Total Capital Deployed</div>
                <div style="font-size: 1.6rem; font-weight: 700; color: var(--accent-emerald); font-family: monospace;">${formatMoney(cumulative)}</div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">Cumulative cash contributions to date</div>
            </div>

            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 1.25rem;">
                <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Contribution Cycles</div>
                <div style="font-size: 1.6rem; font-weight: 700; color: var(--text-primary); font-family: monospace;">${logEntries.length}</div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">Total distinct funding events</div>
            </div>
        </div>

        <!-- Timeline Log Table -->
        <div class="card">
            <h4 style="margin: 0 0 1rem 0; font-size: 0.95rem; color: var(--text-primary);">Point-in-Time Deployed Capital Log</h4>
            <div class="table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Deployment Date</th>
                            <th>Fund / Entity Target</th>
                            <th>Call/Contribution Type</th>
                            <th style="text-align: right;">Funding Deployed</th>
                            <th style="text-align: right;">Cumulative Deployed</th>
                        </tr>
                    </thead>
                    <tbody>
    `;

    displayEntries.forEach(entry => {
        html += `
            <tr>
                <td style="font-family: monospace; font-size: 0.85rem; color: var(--text-primary);">${entry.date}</td>
                <td><strong>${entry.fund}</strong></td>
                <td><span class="type-badge transaction" style="font-size: 0.75rem; background: rgba(59, 130, 246, 0.1); color: var(--accent-blue);">${entry.type}</span></td>
                <td style="text-align: right; font-weight: 600; font-family: monospace; color: var(--accent-emerald);">+${formatMoney(entry.amount)}</td>
                <td style="text-align: right; font-weight: 700; font-family: monospace; color: var(--text-primary);">${formatMoney(entry.cumulative)}</td>
            </tr>
        `;
    });

    html += `
                    </tbody>
                </table>
            </div>
        </div>
    `;

    container.innerHTML = html;
}

function renderTransactionsUi(records, container) {
    let html = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Transaction Date</th>
                    <th>Asset / Investment ID</th>
                    <th>Description</th>
                    <th>Direction</th>
                    <th style="text-align:right;">Amount</th>
                </tr>
            </thead>
            <tbody>
    `;

    records.forEach(r => {
        const isOutflow = r.tr_direction === 'Outflow';
        const color = isOutflow ? 'var(--accent-rose)' : 'var(--accent-emerald)';
        const prefix = isOutflow ? '-' : '+';
        html += `
            <tr>
                <td>${r.tr_date || '—'}</td>
                <td><strong>${r.investment_id}</strong></td>
                <td>${r.name || 'Investment Transaction'}</td>
                <td><span class="status-badge ${isOutflow ? 'fail' : 'pass'}">${r.tr_direction}</span></td>
                <td style="text-align:right; font-weight:600; color:${color};">${r.amount ? prefix + formatMoney(r.amount) : '—'}</td>
            </tr>
        `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
}

function renderCertificatesUi(records, container) {
    let html = `<div class="certificate-grid">`;
    records.forEach(r => {
        const status = (r.cert_status || 'Active').toLowerCase();
        html += `
            <div class="certificate-card">
                <div class="certificate-header">
                    <div class="certificate-title">Share Certificate</div>
                    <div class="certificate-number">${r.cert_number || 'CS-unknown'}</div>
                </div>
                <div class="certificate-body">
                    <div class="certificate-meta" style="font-size:0.65rem; text-transform:uppercase; letter-spacing:0.04em;">This certifies that</div>
                    <div class="certificate-holder" style="font-family:Georgia, serif; font-style:italic;">Carta Demo Dashboard</div>
                    <div class="certificate-meta">holds securities in asset registry group:</div>
                    <div class="certificate-holder" style="font-size:0.85rem; font-family:monospace; color:#fbbf24;">${r.investment_id}</div>
                    <div class="certificate-meta" style="margin-top:0.4rem;">Issued on: <strong>${r.issue_date || '—'}</strong></div>
                </div>
                <div class="certificate-footer">
                    <div class="certificate-seal"></div>
                    <div class="certificate-status-pill ${status === 'active' || status === 'outstanding' ? 'active' : 'cancelled'}">${r.cert_status || 'Active'}</div>
                </div>
            </div>
        `;
    });
    html += `</div>`;
    container.innerHTML = html;
}

function renderDistributionsUi(records, container) {
    if (!Array.isArray(records)) {
        records = [records];
    }
    const firstRec = records[0];
    if (!firstRec) return;

    // Check if it's raw transactions payload
    const isRaw = firstRec.transaction_date !== undefined || firstRec.transaction_type !== undefined || firstRec.cash_cents !== undefined;

    if (!isRaw) {
        // Fallback to standard canonical distribution list
        let html = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Asset / Investment ID</th>
                        <th>LP Stakeholder Reference</th>
                        <th style="text-align:right;">Distribution Amount</th>
                    </tr>
                </thead>
                <tbody>
        `;

        records.forEach(r => {
            html += `
                <tr>
                    <td><strong>${r.investment_id || '—'}</strong></td>
                    <td>${r.lp_name || 'LP Stakeholder'}</td>
                    <td style="text-align:right; font-weight:600; color:var(--accent-emerald); font-family:monospace;">${r.total_amount ? formatMoney(r.total_amount) : '—'}</td>
                </tr>
            `;
        });

        html += `</tbody></table>`;
        container.innerHTML = html;
        return;
    }

    // It's raw transaction records!
    const parseDate = (dStr) => {
        if (!dStr) return new Date(0);
        const parts = dStr.split('/');
        if (parts.length === 3) {
            return new Date(parseInt(parts[2]), parseInt(parts[0]) - 1, parseInt(parts[1]));
        }
        return new Date(dStr);
    };

    const sortedRaw = [...records].sort((a, b) => parseDate(a.transaction_date) - parseDate(b.transaction_date));

    let totalDistributions = 0;
    const distEntries = [];

    sortedRaw.forEach(r => {
        const type = (r.transaction_type || '').toLowerCase();
        const isDist = type.includes('distribution') || type.includes('return of capital') || type.includes('dividend') || type.includes('redemption') || type.includes('liquidation');

        if (isDist) {
            const amt = parseFloat(r.amount) || 0;
            totalDistributions += amt;
            distEntries.push({
                date: r.transaction_date || '—',
                fund: r.fund_name || `Fund #${r.fund_id || '—'}`,
                type: r.transaction_type || 'Distribution',
                amount: amt
            });
        }
    });

    if (distEntries.length === 0) {
        container.innerHTML = `
            <!-- Summary Stats (Zero State) -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
                <div style="background: rgba(255, 255, 255, 0.01); border: 1px dashed var(--border); border-radius: var(--radius-sm); padding: 1.25rem;">
                    <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Total Distributed Capital</div>
                    <div style="font-size: 1.6rem; font-weight: 700; color: var(--text-muted); font-family: monospace;">$0.00</div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">No realized cash returns to date</div>
                </div>

                <div style="background: rgba(255, 255, 255, 0.01); border: 1px dashed var(--border); border-radius: var(--radius-sm); padding: 1.25rem;">
                    <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Distribution Events</div>
                    <div style="font-size: 1.6rem; font-weight: 700; color: var(--text-muted); font-family: monospace;">0</div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">Active holding phase</div>
                </div>
            </div>

            <!-- Zero State Notice -->
            <div style="padding: 3.5rem 1.5rem; text-align: center; border: 1px dashed var(--border); border-radius: var(--radius-sm); background: rgba(255,255,255,0.01);">
                <div style="font-size: 2.2rem; margin-bottom: 0.75rem; filter: grayscale(1);">💰</div>
                <div style="font-weight: 600; font-size: 0.95rem; color: var(--text-primary); margin-bottom: 0.25rem;">No Distribution History Recorded</div>
                <p style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.4; max-width: 380px; margin: 0 auto;">
                    This holding represents active growth-stage private assets. No distribution events, dividend payouts, or share redemptions have occurred for this entity.
                </p>
            </div>
        `;
        return;
    }

    // Sort descending for display (most recent first)
    const displayEntries = [...distEntries].reverse();

    let html = `
        <!-- Timeline Deployed Summary -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
            <div style="background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: var(--radius-sm); padding: 1.25rem;">
                <div style="font-size: 0.7rem; color: var(--accent-emerald); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Total Capital Distributed</div>
                <div style="font-size: 1.6rem; font-weight: 700; color: var(--accent-emerald); font-family: monospace;">${formatMoney(totalDistributions)}</div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">Realized cash returns and redemptions</div>
            </div>

            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 1.25rem;">
                <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Distribution Events</div>
                <div style="font-size: 1.6rem; font-weight: 700; color: var(--text-primary); font-family: monospace;">${distEntries.length}</div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">Total exit/liquidity return events</div>
            </div>
        </div>

        <!-- Distributions Table -->
        <div class="card">
            <h4 style="margin: 0 0 1rem 0; font-size: 0.95rem; color: var(--text-primary);">Realized Distribution Log</h4>
            <div class="table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Distribution Date</th>
                            <th>Fund / Entity Target</th>
                            <th>Transaction Type</th>
                            <th style="text-align: right;">Amount Distributed</th>
                        </tr>
                    </thead>
                    <tbody>
    `;

    displayEntries.forEach(entry => {
        html += `
            <tr>
                <td style="font-family: monospace; font-size: 0.85rem; color: var(--text-primary);">${entry.date}</td>
                <td><strong>${entry.fund}</strong></td>
                <td><span class="type-badge distribution" style="font-size: 0.75rem; background: rgba(16, 185, 129, 0.1); color: var(--accent-emerald);">${entry.type}</span></td>
                <td style="text-align: right; font-weight: 700; font-family: monospace; color: var(--accent-emerald);">${formatMoney(entry.amount)}</td>
            </tr>
        `;
    });

    html += `
                    </tbody>
                </table>
            </div>
        </div>
    `;

    container.innerHTML = html;
}

function renderDefaultTableUi(tableName, records, container) {
    if (records.length === 0) return;
    const keys = Object.keys(records[0]);
    let html = `
        <div style="margin-bottom:0.5rem; font-size:0.8rem; color:var(--text-secondary);">Table: <code>${tableName}</code> (${records.length} records)</div>
        <div class="table-wrap">
            <table class="data-table">
                <thead>
                    <tr>
                        ${keys.map(k => `<th>${k.replace(/_/g, ' ')}</th>`).join('')}
                    </tr>
                </thead>
                <tbody>
    `;

    records.forEach(r => {
        html += `<tr>`;
        keys.forEach(k => {
            const val = r[k];
            if (val === null || val === undefined) {
                html += `<td class="cell-muted">—</td>`;
            } else if (typeof val === 'number') {
                if (k.includes('amount') || k.includes('cost') || k.includes('valuation') || k.includes('value') || k.includes('post_money')) {
                    html += `<td style="font-weight:600;">${formatMoney(val)}</td>`;
                } else {
                    html += `<td>${val}</td>`;
                }
            } else {
                html += `<td>${val}</td>`;
            }
        });
        html += `</tr>`;
    });

    html += `</tbody></table></div>`;
    container.innerHTML = html;
}

function renderCoverageUi(data, container) {
    const summary = data.summary || {};
    const tables = data.tables || {};
    const overallPct = summary.overall_field_coverage_pct || 0;

    let html = `
        <div class="coverage-progress-container">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:600; font-size:0.95rem;">Overall Data Schema Coverage</span>
                <span style="font-weight:700; font-size:1.25rem; color:var(--accent-cyan);">${overallPct}%</span>
            </div>
            <div class="coverage-progress-bar-wrap">
                <div class="coverage-progress-bar-fill" style="width:${overallPct}%;"></div>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-top:0.75rem;">
                <div style="background:rgba(0,0,0,0.2); padding:0.5rem; border-radius:4px; text-align:center;">
                    <div style="font-size:1.2rem; font-weight:700; color:var(--accent-emerald);">${summary.tables_with_data || 0}</div>
                    <div style="font-size:0.68rem; color:var(--text-muted); text-transform:uppercase;">Tables Populated</div>
                </div>
                <div style="background:rgba(0,0,0,0.2); padding:0.5rem; border-radius:4px; text-align:center;">
                    <div style="font-size:1.2rem; font-weight:700; color:var(--accent-rose);">${summary.tables_empty || 0}</div>
                    <div style="font-size:0.68rem; color:var(--text-muted); text-transform:uppercase;">Tables Empty / Stub</div>
                </div>
            </div>
        </div>
        
        <table class="data-table">
            <thead>
                <tr>
                    <th>Table Name</th>
                    <th>Records</th>
                    <th>Populated Fields</th>
                    <th style="text-align:right;">Field Coverage</th>
                </tr>
            </thead>
            <tbody>
    `;

    Object.entries(tables).forEach(([name, t]) => {
        const isStub = t.status === 'EMPTY';
        const color = isStub ? 'var(--text-muted)' : t.coverage_pct >= 70 ? 'var(--accent-emerald)' : 'var(--accent-amber)';
        html += `
            <tr>
                <td><strong>${name}</strong></td>
                <td><span class="type-badge ${isStub ? 'entity' : 'fund'}">${t.record_count || 0} recs</span></td>
                <td class="cell-muted">${t.populated || 0} / ${t.total_fields || 0} fields</td>
                <td style="text-align:right; font-weight:700; color:${color};">${t.coverage_pct}%</td>
            </tr>
        `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
}


async function triggerLiveSync(orgName, targets = null) {
    const modal = document.getElementById('extractionProgressModal');
    const logsContainer = document.getElementById('extractionLogsContainer');
    const progressCompany = document.getElementById('extractionProgressCompany');
    const progressTaskId = document.getElementById('extractionProgressTaskId');
    const progressStatus = document.getElementById('extractionProgressStatus');
    const progressTitle = document.getElementById('extractionProgressTitle');

    progressCompany.textContent = orgName;
    progressTaskId.textContent = 'Submitting task...';
    progressStatus.textContent = 'PENDING';
    progressStatus.className = 'badge';
    progressStatus.style.background = 'var(--accent-amber)';
    progressStatus.style.color = '#000';

    if (targets && targets.length > 0) {
        if (progressTitle) progressTitle.textContent = `Targeted Sync: ${targets.join(', ')}`;
        logsContainer.innerHTML = `<div style="color: var(--border);">Submitting targeted task for [${targets.join(', ')}] to background worker...</div>`;
    } else {
        if (progressTitle) progressTitle.textContent = 'Carta Browser Automation in Progress...';
        logsContainer.innerHTML = '<div style="color: var(--border);">Submitting full task to background worker...</div>';
    }
    
    modal.classList.add('active');

    try {
        const res = await fetch('/api/download-report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ company_name: orgName, targets: targets })
        });
        if (!res.ok) {
            throw new Error(`HTTP error ${res.status}`);
        }
        const taskInfo = await res.json();
        const taskId = taskInfo.task_id;
        currentSyncTaskId = taskId;
        progressTaskId.textContent = `Task ID: ${taskId}`;
        logsContainer.innerHTML += `<div>Task successfully queued: ${taskId}</div>`;

        // Start polling status
        startSyncPolling(taskId);
    } catch (err) {
        progressStatus.textContent = 'FAILED';
        progressStatus.style.background = 'var(--accent-rose)';
        progressStatus.style.color = '#fff';
        logsContainer.innerHTML += `<div style="color: var(--accent-rose); font-weight: bold; margin-top: 0.5rem;">Submission failed: ${err.message}</div>`;
    }
}

function startSyncPolling(taskId) {
    if (syncPollInterval) clearInterval(syncPollInterval);
    const logsContainer = document.getElementById('extractionLogsContainer');
    const progressStatus = document.getElementById('extractionProgressStatus');
    const activeIndicator = document.getElementById('syncActiveIndicator');

    syncPollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/status/${taskId}`);
            if (!res.ok) {
                throw new Error(`HTTP error ${res.status}`);
            }
            const statusData = await res.json();
            const status = (statusData.status || '').toLowerCase();
            
            // Update UI status badge
            progressStatus.textContent = status.toUpperCase();
            if (status === 'completed') {
                progressStatus.style.background = 'var(--accent-emerald)';
                progressStatus.style.color = '#000';
                clearInterval(syncPollInterval);
                currentSyncTaskId = null;
                activeIndicator.style.display = 'none';
                
                // Reload dashboard data dynamically
                try {
                    const reloadRes = await fetch('data/business_data.json');
                    DATA = await reloadRes.json();
                    renderSidebar();
                    renderOverview();
                    renderFunds();
                    renderSPVs();
                    renderInvestments();
                    renderInvestors();
                    renderDocuments();
                    renderExports();
                    renderEntityGraph();
                    renderPipeline();
                    renderRelationships();
                    renderTesting();
                    
                    // Re-inspect current endpoint to show updated value
                    const activeItem = document.querySelector('.platform-endpoint-item.active');
                    if (activeItem) {
                        const idx = parseInt(activeItem.dataset.idx);
                        inspectEndpoint(platformEndpoints[idx]);
                    }
                } catch (e) {
                    console.error("Failed to reload data: ", e);
                }
            } else if (status === 'failed' || status === 'timeout' || status === 'failed_interrupted') {
                progressStatus.style.background = 'var(--accent-rose)';
                progressStatus.style.color = '#fff';
                clearInterval(syncPollInterval);
                currentSyncTaskId = null;
                activeIndicator.style.display = 'none';
            } else {
                progressStatus.style.background = 'var(--accent-blue)';
                progressStatus.style.color = '#fff';
            }

            // Fetch live server logs
            const logsRes = await fetch(`/api/logs/${taskId}`);
            if (logsRes.ok) {
                const logsData = await logsRes.json();
                const logs = logsData.logs || [];
                if (logs.length > 0) {
                    logsContainer.innerHTML = logs.map(line => {
                        let colorStyle = '';
                        if (line.includes('[ERROR]') || line.includes('error') || line.includes('Failed')) {
                            colorStyle = 'color: var(--accent-rose);';
                        } else if (line.includes('[SUCCESS]') || line.includes('success') || line.includes('Completed')) {
                            colorStyle = 'color: var(--accent-emerald);';
                        } else if (line.includes('[WARNING]') || line.includes('warning')) {
                            colorStyle = 'color: var(--accent-amber);';
                        }
                        return `<div style="${colorStyle}">${line}</div>`;
                    }).join('');
                    
                    // Auto scroll
                    logsContainer.scrollTop = logsContainer.scrollHeight;
                }
            }
        } catch (err) {
            console.error('Polling error: ', err);
        }
    }, 2000);
}

function renderCapitalAccountSummaryUi(records, container) {
    if (!Array.isArray(records)) {
        records = [records];
    }
    
    // Helper to get numeric value from potential raw object or number
    const getValue = (val) => {
        if (val === null || val === undefined) return null;
        if (typeof val === 'object') {
            const inner = val.total !== undefined ? val.total : (val.lp !== undefined ? val.lp : null);
            return inner !== null ? parseFloat(inner) : null;
        }
        return parseFloat(val);
    };

    const firstRec = records[0];
    if (!firstRec) return;

    const beg = getValue(firstRec.beginning_balance);
    const ytdBeg = getValue(firstRec.ytd_beginning_balance);
    const end = getValue(firstRec.ending_balance);
    
    // Extracting called / contributions / totals
    const calledPeriod = getValue(firstRec.called_during_period);
    const calledYtd = getValue(firstRec.called_ytd);
    const calledInception = getValue(firstRec.called_from_inception);

    const contribPeriod = getValue(firstRec.contributions_outside_commitment_period);
    const contribYtd = getValue(firstRec.contributions_outside_commitment_ytd);
    const contribInception = getValue(firstRec.contributions_outside_commitment_inception);

    const totalPeriod = getValue(firstRec.total_contributions_period);
    const totalYtd = getValue(firstRec.total_contributions_ytd);
    const totalInception = getValue(firstRec.total_contributions_inception);

    const totalCommitment = getValue(firstRec.total_commitment);
    const recallableDist = getValue(firstRec.recallable_distribution_balance);
    const receivableBal = getValue(firstRec.receivable_balance);
    const deferredBal = getValue(firstRec.deferred_balance);
    const isTransferred = firstRec.commitment_is_transferred;

    const fundName = firstRec.fund_name || firstRec.investment_id || 'Unknown Fund';
    const partnerName = firstRec.partner_name || 'EAI Space I LLC';
    const partnerClassName = firstRec.partner_class_name || '';
    const partnerId = firstRec.partner_id || '—';
    const partnerType = firstRec.partner_type || '—';

    let html = `
        <!-- Profile / Meta Header -->
        <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 1.25rem; margin-bottom: 1.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <span style="font-size: 0.75rem; text-transform: uppercase; color: var(--accent-cyan); font-weight: 600; letter-spacing: 0.05em;">Capital Account Overview</span>
                    <h3 style="margin: 0.25rem 0 0.5rem 0; font-size: 1.3rem; color: var(--text-primary);">${fundName}</h3>
                    <div style="display: flex; gap: 1.5rem; flex-wrap: wrap; font-size: 0.82rem; color: var(--text-secondary);">
                        <div><strong>Partner:</strong> ${partnerName} (ID: ${partnerId})</div>
                        <div><strong>Class:</strong> ${partnerClassName || '—'}</div>
                        <div><strong>Type:</strong> ${partnerType}</div>
                    </div>
                </div>
                <div style="text-align: right; font-size: 0.82rem; color: var(--text-secondary);">
                    <div><strong>Sharing Date:</strong> ${firstRec.information_sharing_date || '—'}</div>
                    <div style="margin-top: 0.25rem;"><strong>Commitment Transferred:</strong> <span class="coverage-status ${isTransferred ? 'partial' : 'full'}">${isTransferred ? 'YES' : 'NO'}</span></div>
                </div>
            </div>
        </div>

        <!-- Key Balances Grid -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 1rem;">
                <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem;">Beginning Balance (Period)</div>
                <div style="font-size: 1.3rem; font-weight: 700; color: var(--text-primary); font-family: monospace;">${beg !== null ? formatMoney(beg) : '—'}</div>
            </div>
            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 1rem;">
                <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem;">Beginning Balance (YTD)</div>
                <div style="font-size: 1.3rem; font-weight: 700; color: var(--text-primary); font-family: monospace;">${ytdBeg !== null ? formatMoney(ytdBeg) : '—'}</div>
            </div>
            <div style="background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: var(--radius-sm); padding: 1rem;">
                <div style="font-size: 0.7rem; color: var(--accent-emerald); text-transform: uppercase; margin-bottom: 0.35rem;">Ending Balance</div>
                <div style="font-size: 1.3rem; font-weight: 700; color: var(--accent-emerald); font-family: monospace;">${end !== null ? formatMoney(end) : '—'}</div>
            </div>
            <div style="background: rgba(139, 92, 246, 0.05); border: 1px solid rgba(139, 92, 246, 0.2); border-radius: var(--radius-sm); padding: 1rem;">
                <div style="font-size: 0.7rem; color: var(--accent-violet); text-transform: uppercase; margin-bottom: 0.35rem;">Total Commitment</div>
                <div style="font-size: 1.3rem; font-weight: 700; color: var(--accent-violet); font-family: monospace;">${totalCommitment !== null ? formatMoney(totalCommitment) : '—'}</div>
            </div>
        </div>

        <!-- Additional Balances Detail -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.85rem; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 0.75rem; color: var(--text-secondary);">Deferred Balance:</span>
                <span style="font-weight: 600; font-family: monospace; color: ${deferredBal > 0 ? 'var(--accent-amber)' : 'var(--text-primary)'};">${deferredBal !== null ? formatMoney(deferredBal) : '—'}</span>
            </div>
            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.85rem; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 0.75rem; color: var(--text-secondary);">Receivable Balance:</span>
                <span style="font-weight: 600; font-family: monospace; color: ${receivableBal > 0 ? 'var(--accent-rose)' : 'var(--text-primary)'};">${receivableBal !== null ? formatMoney(receivableBal) : '—'}</span>
            </div>
            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.85rem; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 0.75rem; color: var(--text-secondary);">Recallable Dist. Balance:</span>
                <span style="font-weight: 600; font-family: monospace; color: var(--text-primary);">${recallableDist !== null ? formatMoney(recallableDist) : '—'}</span>
            </div>
        </div>

        <!-- Commitment & Capital Ledger comparison table -->
        <div style="margin-bottom: 1.5rem;">
            <div style="font-weight: 600; font-size: 0.95rem; color: var(--text-primary); margin-bottom: 0.50rem;">Capital Activity Ledger</div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Activity Classification</th>
                        <th style="text-align:right;">During Period</th>
                        <th style="text-align:right;">Year to Date (YTD)</th>
                        <th style="text-align:right;">Inception to Date</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Called Capital</strong></td>
                        <td style="text-align:right; font-family:monospace;">${calledPeriod !== null ? formatMoney(calledPeriod) : '—'}</td>
                        <td style="text-align:right; font-family:monospace;">${calledYtd !== null ? formatMoney(calledYtd) : '—'}</td>
                        <td style="text-align:right; font-family:monospace; font-weight:600;">${calledInception !== null ? formatMoney(calledInception) : '—'}</td>
                    </tr>
                    <tr>
                        <td><strong>Contributions Outside Commitment</strong></td>
                        <td style="text-align:right; font-family:monospace;">${contribPeriod !== null ? formatMoney(contribPeriod) : '—'}</td>
                        <td style="text-align:right; font-family:monospace;">${contribYtd !== null ? formatMoney(contribYtd) : '—'}</td>
                        <td style="text-align:right; font-family:monospace; font-weight:600;">${contribInception !== null ? formatMoney(contribInception) : '—'}</td>
                    </tr>
                    <tr style="border-top: 1px solid var(--border); background: rgba(255,255,255,0.01);">
                        <td><strong>Total Contributions</strong></td>
                        <td style="text-align:right; font-family:monospace; font-weight:600;">${totalPeriod !== null ? formatMoney(totalPeriod) : '—'}</td>
                        <td style="text-align:right; font-family:monospace; font-weight:600;">${totalYtd !== null ? formatMoney(totalYtd) : '—'}</td>
                        <td style="text-align:right; font-family:monospace; font-weight:700; color:var(--accent-cyan);">${totalInception !== null ? formatMoney(totalInception) : '—'}</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- Dynamic Transaction Tabs -->
        <div>
            <div style="display: flex; border-bottom: 1px solid var(--border); margin-bottom: 1rem; gap: 0.5rem;">
                <button id="btn-cap-period" class="cap-acc-tab-btn active" onclick="switchCapitalAccountTab('period')" style="background:transparent; border:none; border-bottom:2px solid var(--accent-cyan); color:var(--text-primary); padding:0.5rem 1rem; cursor:pointer; font-weight:600; font-size:0.85rem; transition: all 0.2s;">
                    Period Transactions (${(firstRec.transactions_during_period || []).length})
                </button>
                <button id="btn-cap-ytd" class="cap-acc-tab-btn" onclick="switchCapitalAccountTab('ytd')" style="background:transparent; border:none; border-bottom:2px solid transparent; color:var(--text-secondary); padding:0.5rem 1rem; cursor:pointer; font-weight:600; font-size:0.85rem; transition: all 0.2s;">
                    YTD Transactions (${(firstRec.ytd_transactions || []).length})
                </button>
                <button id="btn-cap-all" class="cap-acc-tab-btn" onclick="switchCapitalAccountTab('all')" style="background:transparent; border:none; border-bottom:2px solid transparent; color:var(--text-secondary); padding:0.5rem 1rem; cursor:pointer; font-weight:600; font-size:0.85rem; transition: all 0.2s;">
                    All-Time Transactions (${(firstRec.all_time_transactions || []).length})
                </button>
            </div>

            <!-- Tab Content 1: Period -->
            <div id="tab-cap-period" class="cap-acc-tab-content" style="display: block;">
                ${renderTransactionsSubTable(firstRec.transactions_during_period, getValue)}
            </div>

            <!-- Tab Content 2: YTD -->
            <div id="tab-cap-ytd" class="cap-acc-tab-content" style="display: none;">
                ${renderTransactionsSubTable(firstRec.ytd_transactions, getValue)}
            </div>

            <!-- Tab Content 3: All-Time -->
            <div id="tab-cap-all" class="cap-acc-tab-content" style="display: none;">
                ${renderTransactionsSubTable(firstRec.all_time_transactions, getValue)}
            </div>
        </div>
    `;

    container.innerHTML = html;
}

window.switchCapitalAccountTab = function(tabName) {
    document.querySelectorAll('.cap-acc-tab-btn').forEach(btn => {
        btn.classList.remove('active');
        btn.style.borderBottomColor = 'transparent';
        btn.style.color = 'var(--text-secondary)';
    });
    document.querySelectorAll('.cap-acc-tab-content').forEach(c => c.style.display = 'none');
    
    const activeBtn = document.getElementById('btn-cap-' + tabName);
    const activeContent = document.getElementById('tab-cap-' + tabName);
    if (activeBtn) {
        activeBtn.classList.add('active');
        activeBtn.style.borderBottomColor = 'var(--accent-cyan)';
        activeBtn.style.color = 'var(--text-primary)';
    }
    if (activeContent) {
        activeContent.style.display = 'block';
    }
};

function renderTransactionsSubTable(transactions, getValue) {
    if (!Array.isArray(transactions) || transactions.length === 0) {
        return `
            <div style="padding: 2.5rem; text-align: center; color: var(--text-muted); font-size: 0.85rem; border: 1px dashed var(--border); border-radius: var(--radius-sm); background: rgba(255,255,255,0.01);">
                No transactions recorded for this scope.
            </div>
        `;
    }

    let subHtml = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Transaction Type / Allocation</th>
                    <th style="text-align:right;">LP Amount</th>
                    <th style="text-align:right;">GP Amount</th>
                    <th style="text-align:right;">Total Allocation</th>
                </tr>
            </thead>
            <tbody>
    `;

    transactions.forEach(tx => {
        const lpVal = getValue(tx.lp);
        const gpVal = getValue(tx.gp);
        const totalVal = getValue(tx.total);
        const isNegative = totalVal < 0;
        const color = isNegative ? 'var(--accent-rose)' : 'var(--accent-emerald)';
        const prefix = totalVal >= 0 ? '+' : '';
        
        subHtml += `
            <tr>
                <td><strong>${tx.type}</strong></td>
                <td style="text-align:right; font-family:monospace;">${lpVal !== null ? formatMoney(lpVal) : '—'}</td>
                <td style="text-align:right; font-family:monospace; color:var(--text-muted);">${gpVal !== null ? formatMoney(gpVal) : '—'}</td>
                <td style="text-align:right; font-weight:600; color:${color};">${totalVal !== null ? prefix + formatMoney(totalVal) : '—'}</td>
            </tr>
        `;
    });

    subHtml += `</tbody></table>`;
    return subHtml;
}

function renderPartnerMetricsUi(records, container) {
    if (!Array.isArray(records)) {
        records = [records];
    }
    const firstRec = records[0];
    if (!firstRec) return;

    const partner = firstRec.partner || {};
    const metrics = firstRec.metrics || {};
    const metricsSharing = firstRec.metrics_as_of_sharing_date || {};
    const sharingDate = firstRec.sharing_date || '—';

    const getVal = (val) => {
        if (val === null || val === undefined) return null;
        return parseFloat(val);
    };

    const commitment = getVal(metrics.commitment);
    const called = getVal(metrics.called_capital);
    const contributed = getVal(metrics.capital_contributed);
    const paid = getVal(metrics.capital_contributed_paid);
    const prepaid = getVal(metrics.prepaid_capital_contribution);
    const liabilities = getVal(metrics.capital_call_liabilities);
    const nav = getVal(metrics.net_asset_value);
    const distributions = getVal(metrics.distributions);
    const vintage = metrics.vintage_year || '—';

    const calledPercent = (commitment && commitment > 0 && called !== null) ? ((called / commitment) * 100).toFixed(1) : null;

    let html = `
        <!-- Profile / Meta Header -->
        <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 1.25rem; margin-bottom: 1.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <span style="font-size: 0.75rem; text-transform: uppercase; color: var(--accent-cyan); font-weight: 600; letter-spacing: 0.05em;">Partner Metrics Profile</span>
                    <h3 style="margin: 0.25rem 0 0.5rem 0; font-size: 1.3rem; color: var(--text-primary);">${partner.name || 'EAI Space I LLC'}</h3>
                    <div style="display: flex; gap: 1.5rem; flex-wrap: wrap; font-size: 0.82rem; color: var(--text-secondary);">
                        <div><strong>Partner ID:</strong> ${partner.id || '—'}</div>
                        <div><strong>Partner Type:</strong> <span class="type-badge fund">${partner.partner_type || 'member'}</span></div>
                        <div><strong>Firm:</strong> ${partner.firm_name || 'Aliya Capital Partners'}</div>
                    </div>
                </div>
                <div style="text-align: right; font-size: 0.82rem; color: var(--text-secondary);">
                    <div><strong>Sharing Date:</strong> ${sharingDate}</div>
                    <div style="margin-top: 0.25rem;"><strong>Vintage Year:</strong> <span style="font-weight:600; color:var(--text-primary);">${vintage}</span></div>
                </div>
            </div>
            
            <div style="margin-top: 1rem; border-top: 1px solid var(--border); padding-top: 0.75rem; display: flex; gap: 1.5rem; font-size: 0.78rem; color: var(--text-muted);">
                <div><strong>Portal Access Sent:</strong> ${partner.sent_date ? new Date(partner.sent_date).toLocaleDateString() : '—'}</div>
                <div><strong>Portal Access Accepted:</strong> ${partner.accepted_date ? new Date(partner.accepted_date).toLocaleDateString() : '—'}</div>
            </div>
        </div>

        <!-- Key Metrics Cards -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
            <div style="background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: var(--radius-sm); padding: 1.25rem; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="font-size: 0.7rem; color: var(--accent-emerald); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Net Asset Value (NAV)</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: var(--accent-emerald); font-family: monospace;">${nav !== null ? formatMoney(nav) : '—'}</div>
                </div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">Total Value of Partner Share</div>
            </div>

            <div style="background: rgba(139, 92, 246, 0.05); border: 1px solid rgba(139, 92, 246, 0.2); border-radius: var(--radius-sm); padding: 1.25rem;">
                <div style="font-size: 0.7rem; color: var(--accent-violet); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Capital Commitment</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: var(--accent-violet); font-family: monospace;">${commitment !== null ? formatMoney(commitment) : '—'}</div>
                ${calledPercent !== null ? `
                    <div style="margin-top: 0.6rem;">
                        <div style="display: flex; justify-content: space-between; font-size: 0.7rem; color: var(--text-secondary); margin-bottom: 0.25rem;">
                            <span>Called Progress</span>
                            <span>${calledPercent}%</span>
                        </div>
                        <div style="background: rgba(255,255,255,0.05); border-radius: 4px; height: 6px; overflow: hidden; width: 100%;">
                            <div style="background: var(--accent-violet); width: ${calledPercent}%; height: 100%; border-radius: 4px;"></div>
                        </div>
                    </div>
                ` : ''}
            </div>

            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 1.25rem;">
                <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Called Capital</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: var(--text-primary); font-family: monospace;">${called !== null ? formatMoney(called) : '—'}</div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">Uncalled Commitment: <strong>${(commitment !== null && called !== null) ? formatMoney(commitment - called) : '—'}</strong></div>
            </div>

            <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 1.25rem;">
                <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.35rem; font-weight: 600;">Total Distributions</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: var(--text-primary); font-family: monospace;">${distributions !== null ? formatMoney(distributions) : '—'}</div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">DPI (Distributions / Capital Paid): <strong>${(distributions !== null && paid && paid > 0) ? (distributions / paid).toFixed(2) + 'x' : '0.00x'}</strong></div>
            </div>
        </div>

        <!-- Ledger & Liabilities Table -->
        <div class="card" style="margin-bottom: 1.5rem;">
            <h4 style="margin: 0 0 1rem 0; font-size: 0.95rem; color: var(--text-primary);">Detailed Account Ledger & Balances</h4>
            <div class="table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Performance Metric</th>
                            <th style="text-align: right;">Cumulative Value</th>
                            <th style="text-align: right;">As of Sharing Date</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><strong>Capital Contributed</strong></td>
                            <td style="text-align: right; font-weight: 600; font-family: monospace; color: var(--text-primary);">${contributed !== null ? formatMoney(contributed) : '—'}</td>
                            <td style="text-align: right; font-family: monospace; color: var(--text-secondary);">${metricsSharing.capital_contributed ? formatMoney(parseFloat(metricsSharing.capital_contributed)) : '—'}</td>
                            <td class="cell-muted" style="font-size: 0.8rem;">Total capital drawn down and credited to the capital account.</td>
                        </tr>
                        <tr>
                            <td><strong>Capital Contributed (Paid)</strong></td>
                            <td style="text-align: right; font-weight: 600; font-family: monospace; color: var(--accent-emerald);">${paid !== null ? formatMoney(paid) : '—'}</td>
                            <td style="text-align: right; font-family: monospace; color: var(--text-secondary);">${metricsSharing.capital_contributed_paid ? formatMoney(parseFloat(metricsSharing.capital_contributed_paid)) : '—'}</td>
                            <td class="cell-muted" style="font-size: 0.8rem;">Cash contribution amount successfully cleared/paid by the partner.</td>
                        </tr>
                        <tr>
                            <td><strong>Capital Call Liabilities</strong></td>
                            <td style="text-align: right; font-weight: 600; font-family: monospace; color: ${liabilities > 0 ? 'var(--accent-rose)' : 'var(--text-primary)'};">${liabilities !== null ? formatMoney(liabilities) : '—'}</td>
                            <td style="text-align: right; font-family: monospace; color: var(--text-secondary);">${metricsSharing.capital_call_liabilities ? formatMoney(parseFloat(metricsSharing.capital_call_liabilities)) : '—'}</td>
                            <td class="cell-muted" style="font-size: 0.8rem; color: ${liabilities > 0 ? 'var(--accent-rose)' : 'var(--text-muted)'};">${liabilities > 0 ? '⚠️ Outstanding unpaid capital calls' : 'No outstanding liabilities.'}</td>
                        </tr>
                        <tr>
                            <td><strong>Prepaid Capital Contribution</strong></td>
                            <td style="text-align: right; font-weight: 600; font-family: monospace; color: var(--text-primary);">${prepaid !== null ? formatMoney(prepaid) : '—'}</td>
                            <td style="text-align: right; font-family: monospace; color: var(--text-secondary);">${metricsSharing.prepaid_capital_contribution ? formatMoney(parseFloat(metricsSharing.prepaid_capital_contribution)) : '—'}</td>
                            <td class="cell-muted" style="font-size: 0.8rem;">Excess/advance payments made by the partner before a call.</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    `;

    container.innerHTML = html;
}

document.addEventListener('DOMContentLoaded', init);
