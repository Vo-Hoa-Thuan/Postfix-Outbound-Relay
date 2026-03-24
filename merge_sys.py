import os

def merge():
    base_dir = r"d:\mailp\Postfix-Outbound-Relay\templates"
    diag_file = os.path.join(base_dir, "diagnostics.html")
    rspamd_file = os.path.join(base_dir, "rspamd.html")
    
    with open(diag_file, "r", encoding="utf-8") as f:
        diag_content = f.read()
    with open(rspamd_file, "r", encoding="utf-8") as f:
        rspamd_content = f.read()
        
    # Extract blocks from diagnostics
    # content block:
    d_cont_start = diag_content.find("{% block content %}") + len("{% block content %}")
    d_cont_end = diag_content.find("{% endblock %}", d_cont_start)
    diag_body = diag_content[d_cont_start:d_cont_end].strip()
    
    d_script_start = diag_content.find("{% block scripts %}")
    if d_script_start != -1:
        d_script_start += len("{% block scripts %}")
        d_script_end = diag_content.find("{% endblock %}", d_script_start)
        diag_scripts = diag_content[d_script_start:d_script_end].strip()
    else:
        diag_scripts = ""
        
    # Extract blocks from rspamd
    r_cont_start = rspamd_content.find("{% block content %}") + len("{% block content %}")
    r_cont_end = rspamd_content.find("{% endblock %}", r_cont_start)
    rspamd_body = rspamd_content[r_cont_start:r_cont_end].strip()
    
    # Rspamd has no block scripts usually, but if it does:
    r_script_start = rspamd_content.find("{% block scripts %}")
    if r_script_start != -1:
        r_script_start += len("{% block scripts %}")
        r_script_end = rspamd_content.find("{% endblock %}", r_script_start)
        rspamd_scripts = rspamd_content[r_script_start:r_script_end].strip()
    else:
        rspamd_scripts = ""

    # Remove the section headers to avoid duplication of titles, we use tabs
    diag_body = diag_body.replace('<div class="section-header">\n    <h2 style="color: var(--accent); font-size: 1.1rem; letter-spacing: 0.1em; text-transform: uppercase;" data-i18n="ttl_diag_tools">🩺 System Diagnostics</h2>\n</div>', '')
    rspamd_body = rspamd_body.replace('<div class="section-header">\n    <h2 style="color: var(--accent); font-size: 1.1rem; letter-spacing: 0.1em; text-transform: uppercase;" data-i18n="ttl_rspamd_main">🛡️ Anti-Spam (Rspamd) Operational Control</h2>\n</div>', '')

    out = f"""{{% extends "base.html" %}}
{{% set active_page = "diagnostics" %}}

{{% block title %}}System & Diagnostics – Operations Console{{% endblock %}}

{{% block content %}}
<div class="tabs-container mb-4" style="display: flex; gap: 1rem; border-bottom: 1px solid var(--border); margin-bottom: 1.5rem;">
    <button class="nav-tab active" onclick="switchSysTab('diag')" id="tab-diag" style="background: none; border: none; padding: 0.5rem 1rem; cursor: pointer; font-size: 1.1rem; color: var(--accent); border-bottom: 2px solid var(--accent); outline: none; transition: 0.3s; font-weight: bold;">🩺 System Diagnostics</button>
    <button class="nav-tab" onclick="switchSysTab('rspamd')" id="tab-rspamd" style="background: none; border: none; padding: 0.5rem 1rem; cursor: pointer; font-size: 1.1rem; color: var(--text-muted); border-bottom: 2px solid transparent; outline: none; transition: 0.3s; font-weight: bold;">🛡️ Anti-Spam (Rspamd)</button>
</div>

<div id="content-diag">
    {diag_body}
</div>

<div id="content-rspamd" style="display: none;">
    {rspamd_body}
</div>

<script>
function switchSysTab(tab) {{
    document.getElementById('content-diag').style.display = tab === 'diag' ? 'block' : 'none';
    document.getElementById('content-rspamd').style.display = tab === 'rspamd' ? 'block' : 'none';
    
    document.getElementById('tab-diag').style.color = tab === 'diag' ? 'var(--accent)' : 'var(--text-muted)';
    document.getElementById('tab-diag').style.borderBottomColor = tab === 'diag' ? 'var(--accent)' : 'transparent';
    
    document.getElementById('tab-rspamd').style.color = tab === 'rspamd' ? 'var(--accent)' : 'var(--text-muted)';
    document.getElementById('tab-rspamd').style.borderBottomColor = tab === 'rspamd' ? 'var(--accent)' : 'transparent';
    
    localStorage.setItem('sys_active_tab', tab);
}}

// Persist tab or auto-switch on message
document.addEventListener("DOMContentLoaded", () => {{
    const urlParams = new URLSearchParams(window.location.search);
    const msg = urlParams.get('msg') || urlParams.get('error') || "";
    if (msg.toLowerCase().includes('rspamd')) {{
        switchSysTab('rspamd');
    }} else if (localStorage.getItem('sys_active_tab') === 'rspamd') {{
        switchSysTab('rspamd');
    }}
}});
</script>
{{% endblock %}}

{{% block scripts %}}
{diag_scripts}
{rspamd_scripts}
{{% endblock %}}
"""
    
    with open(diag_file, "w", encoding="utf-8") as f:
        f.write(out)

merge()
