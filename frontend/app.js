// ─── State ───
let DATA = null;

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
        setupNav();
        setupModal();
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
    document.getElementById('firmName').textContent = firm.name || 'Unknown Firm';
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

document.addEventListener('DOMContentLoaded', init);
