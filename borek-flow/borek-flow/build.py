#!/usr/bin/env python3
"""Generates the Borek Flow static pages. Run: python3 build.py"""
import re, pathlib

root = pathlib.Path(__file__).parent
css = (root / "styles.css").read_text()
logo = (root / "logo.svg").read_text()
logo = re.sub(r'\s(width|height)="[^"]*"', "", logo, count=2)  # sized by CSS

CHEV = '<svg class="chev" width="14" height="8" viewBox="0 0 14 8" fill="none" aria-hidden="true"><path d="M1 1L7 7L13 1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
BACK = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M14 8H2.5M7.5 3L2.5 8L7.5 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
DOWNLOAD = '<svg width="12" height="12" viewBox="1293 397 12 12" fill="none" aria-hidden="true"><path d="M1299 397V405M1302 402L1299 405L1296 402M1293 406V409H1305V406" stroke="currentColor" stroke-width="1.4"/></svg>'

PROJECT_TABS = [
    ("overview", "Overview", "project-overview.html"),
    ("milestones", "Milestones", "project-milestones.html"),
    ("reports", "Reports", "project-reports.html"),
    ("stakeholders", "Stakeholders", "project-stakeholders.html"),
]


def shell(title, page_title, nav, body, extra_class=""):
    def navitem(key, label, href):
        cur = ' aria-current="page"' if nav == key else ""
        return f'<a class="nav-item" href="{href}"{cur}>{label}</a>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Borek Flow</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
{css}
</style>
</head>
<body class="{extra_class}">
<aside class="sidebar">
  <a class="brand" href="home.html">
    <span class="brand-logo">{logo}</span>
    <span class="brand-sub">Borek Flow</span>
  </a>
  <nav class="nav" aria-label="Main">
    {navitem("overview", "Overview", "home.html")}
    {navitem("projects", "Projects", "projects.html")}
  </nav>
</aside>
<div class="main">
  <header class="topbar">
    <h1 class="page-title"><span>{page_title}</span></h1>
    <div class="tools">
      <div class="lang" role="group" aria-label="Language"><button type="button" class="lang-btn">DE</button><button type="button" class="lang-btn is-active" aria-pressed="true">EN</button></div>
      <span class="tools-divider" aria-hidden="true"></span>
      <a class="user" href="profile.html"><span class="avatar">ME</span><span class="user-name">Morgan Ellis</span></a>
    </div>
  </header>
  <main class="content">
{body}
  </main>
</div>
</body>
</html>
"""


def project_header(active):
    tabs = "".join(
        f'<a class="tab" href="{href}"{" aria-current=\"page\"" if key == active else ""}>{label}</a>'
        for key, label, href in PROJECT_TABS
    )
    return f"""    <nav class="crumbs" aria-label="Breadcrumb"><a href="projects.html">Projects</a> / <span>Website Redesign</span></nav>
    <div class="project-title"><h2>Website Redesign</h2>{CHEV}</div>
    <nav class="tabs" aria-label="Project sections">{tabs}</nav>"""


def write(name, html):
    (root / name).write_text(html)
    print("wrote", name)


# ---------------------------------------------------------------- Home
home = """    <h2 class="welcome">Welcome back, Morgan</h2>
    <p class="lede">Project progress, upcoming milestones and your change requests.</p>
    <section class="kpis">
      <div class="card kpi-home"><h3>Active projects</h3><p class="n">2</p><p class="cap">Projects shared with you</p></div>
      <div class="card kpi-home"><h3>Requests in review</h3><p class="n">1</p><p class="cap">Awaiting a decision</p></div>
      <div class="card kpi-home"><h3>Upcoming milestones</h3><p class="n">3</p><p class="cap">Across your projects</p></div>
      <div class="card kpi-home"><h3>Reports</h3><p class="n">2</p><p class="cap">Shared and generated reports</p></div>
    </section>
    <div class="home-grid">
      <section class="card projects-card">
        <h3 class="card-title">Your projects</h3>
        <p class="card-sub">2 projects available to you</p>
        <div class="ptable" role="table" aria-label="Your projects">
          <div class="ptable-head" role="row"><span>Project</span><span>Health</span><span>Progress</span></div>
          <div class="prow" role="row">
            <div><a class="plink" href="project-overview.html">Website Redesign</a><p class="cap">Client handover · 06 Nov</p></div>
            <span class="pill pill-green">On track</span>
            <div class="meter"><span class="bar"><i style="width:68%"></i></span><span class="pct">68%</span></div>
          </div>
          <div class="prow" role="row">
            <div><a class="plink" href="projects.html">Customer portal</a><p class="cap">Preview review · 09 Nov</p></div>
            <span class="pill pill-green">On track</span>
            <div class="meter"><span class="bar"><i style="width:45%"></i></span><span class="pct">45%</span></div>
          </div>
        </div>
      </section>
      <section class="card ms-card">
        <h3 class="card-title">Upcoming milestones</h3>
        <ul class="ms-list">
          <li><time>06 Nov</time><div><strong>Client handover</strong><span>Website Redesign</span></div></li>
          <li><time>09 Nov</time><div><strong>Preview review</strong><span>Customer portal</span></div></li>
          <li><time>13 Nov</time><div><strong>Client handover</strong><span>Customer portal</span></div></li>
        </ul>
      </section>
    </div>"""
write("home.html", shell("Home", "Home", "overview", home))

# ---------------------------------------------------------------- Projects
projects = """    <h2 class="h-section">Projects shared with you</h2>
    <p class="lede lede-sm">Only projects you have been invited to are available here.</p>
    <p class="published">Published 02 Nov 2026 · Alex Morgan, Project Manager</p>
    <section class="project-cards">
      <article class="card project-card">
        <div class="pc-head"><h3>Website Redesign</h3><span class="pill pill-green">On track</span></div>
        <p class="pc-line">Published progress · 68%</p>
        <span class="bar bar-lg"><i style="width:68%"></i></span>
        <p class="pc-line">Next milestone: Client handover · 06 Nov 2026</p>
        <a class="btn btn-outline" href="project-overview.html">View project</a>
      </article>
      <article class="card project-card">
        <div class="pc-head"><h3>Customer portal</h3><span class="pill pill-green">On track</span></div>
        <p class="pc-line">Published progress · 45%</p>
        <span class="bar bar-lg"><i style="width:45%"></i></span>
        <p class="pc-line">Next milestone: Preview review · 09 Nov 2026</p>
        <a class="btn btn-outline" href="projects.html">View project</a>
      </article>
    </section>"""
write("projects.html", shell("Projects", "Projects", "projects", projects))

# ---------------------------------------------------------------- Project overview
# donut: r=88, stroke 24 -> circumference 552.92; 68% = 375.987
C = 2 * 3.14159265 * 88
overview = f"""{project_header("overview")}
    <section class="kpis kpis-project">
      <div class="card kpi"><h3>Project health</h3><p class="v v-text">On track</p><p class="cap">Progressing as planned</p></div>
      <div class="card kpi"><h3>Published progress</h3><p class="v">68%</p><p class="cap">Latest shared delivery progress</p></div>
      <div class="card kpi"><h3>Next milestone</h3><p class="v">06 Nov</p><p class="cap">Client handover · Planned</p></div>
      <div class="card kpi"><h3>Change requests</h3><p class="v">1</p><p class="cap">1 in review</p></div>
    </section>
    <div class="two-col">
      <section class="card panel panel-tall">
        <h3 class="card-title">Delivery progress</h3>
        <p class="card-sub">Latest published progress</p>
        <div class="donut-row">
          <div class="donut" role="img" aria-label="68% complete">
            <svg width="200" height="200" viewBox="0 0 200 200"><circle cx="100" cy="100" r="88" fill="none" stroke="#F3F4F8" stroke-width="24"/><circle cx="100" cy="100" r="88" fill="none" stroke="#124F94" stroke-width="24" stroke-dasharray="{C*0.68:.2f} {C:.2f}" transform="rotate(-90 100 100)"/></svg>
            <div class="donut-label"><strong>68%</strong><span>Complete</span></div>
          </div>
          <ul class="legend">
            <li><i class="dot dot-blue"></i><span>Complete</span><b>68%</b></li>
            <li><i class="dot dot-soft"></i><span>Remaining</span><b>32%</b></li>
          </ul>
        </div>
      </section>
      <section class="card panel panel-tall">
        <h3 class="card-title">Change requests</h3>
        <p class="card-sub">1 request in total</p>
        <div class="cr-list">
          <div class="cr"><div class="cr-row"><span>In review</span><b>1</b></div><span class="bar bar-lg"><i style="width:100%"></i></span></div>
          <div class="cr"><div class="cr-row"><span>Approved</span><b>0</b></div><span class="bar bar-lg"><i style="width:0"></i></span></div>
          <div class="cr"><div class="cr-row"><span>Declined</span><b>0</b></div><span class="bar bar-lg"><i style="width:0"></i></span></div>
        </div>
      </section>
    </div>
    <div class="two-col">
      <section class="card panel panel-short">
        <h3 class="card-title">Milestones</h3>
        <ul class="ms-mini">
          <li><time>30 Oct</time><span>Delivery review</span><em class="pill pill-red">Overdue</em></li>
          <li><time>06 Nov</time><span>Client handover</span><em class="pill pill-soft">Planned</em></li>
        </ul>
      </section>
      <section class="card panel panel-short">
        <h3 class="card-title">Latest report</h3>
        <a class="plink" href="project-report-details.html">Delivery status report</a>
      </section>
    </div>"""
write("project-overview.html", shell("Project overview", "Overview", "projects", overview))

# ---------------------------------------------------------------- Milestones
milestones_svg = open(root / "milestone-curve.svg.txt").read()
milestones = f"""{project_header("milestones")}
    <h2 class="h-section h-section-2">Milestones</h2>
    <p class="lede lede-sm lede-ms">Where your project stands, in date order · shared by Alex Morgan, Project Manager</p>
    <section class="ms-board" aria-label="Milestone timeline">
{milestones_svg}
      <article class="ms-node ms-node-1">
        <h3>Delivery review</h3>
        <p class="ms-status ms-late">Running late</p>
        <p>Was due 30 Oct 2026</p>
        <p>New date requested: 2 Nov 2026</p>
        <p class="ms-pct">68% complete</p>
        <span class="bar bar-lg"><i style="width:68%"></i></span>
        <a class="ms-link" href="project-overview.html">See the change request (CR-02)</a>
      </article>
      <article class="ms-node ms-node-2">
        <h3>Client handover</h3>
        <p class="ms-status ms-idle">Not started yet</p>
        <p>Planned for 6 Nov 2026</p>
        <p class="ms-pct">0% complete</p>
        <span class="bar bar-lg"><i style="width:0"></i></span>
      </article>
      <span class="ms-today">Today · 2 Nov</span>
      <ul class="ms-legend">
        <li><svg width="32" height="6" viewBox="32 810 32 6" fill="none" aria-hidden="true"><path d="M34 813H62" stroke="#124F94" stroke-width="4" stroke-linecap="round"/></svg>Done so far</li>
        <li><svg width="32" height="6" viewBox="167 810 32 6" fill="none" aria-hidden="true"><path d="M168.5 813.5H172.125M179.375 813.5H186.625M193.875 813.5H197.5" stroke="#7D879C" stroke-width="3" stroke-linecap="round"/></svg>Still ahead</li>
      </ul>
    </section>"""
write("project-milestones.html", shell("Milestones", "Account Manager", "projects", milestones))

# ---------------------------------------------------------------- Reports
reports = f"""{project_header("reports")}
    <h2 class="h-section h-section-2">Reports</h2>
    <p class="lede lede-sm lede-rep">View published reports shared with your organisation.</p>
    <div class="rtable">
      <div class="rtable-head"><span>Report</span><span>Reporting period</span><span>Created on</span><span>Status</span><span></span></div>
      <div class="rtable-row">
        <a class="plink" href="project-report-details.html">Delivery status report</a>
        <span>24–30 Oct 2026</span>
        <span>30 Oct 2026</span>
        <span class="status">Published</span>
        <a class="dl" href="#download">{DOWNLOAD}Download</a>
      </div>
    </div>
    <p class="foot">Reports include only published information shared with your organisation.</p>"""
write("project-reports.html", shell("Reports", "Account Manager", "projects", reports))

# ---------------------------------------------------------------- Report details
details = f"""{project_header("reports")}
    <a class="back" href="project-reports.html">{BACK}Back</a>
    <h2 class="h-section h-detail">Delivery status report</h2>
    <section class="card detail">
      <p class="by">Published by Alex Morgan · Project Manager</p>
      <dl>
        <dt>Reporting period</dt><dd>24–30 Oct 2026</dd>
        <dt>Created on</dt><dd>30 Oct 2026</dd>
        <dt>Published progress</dt><dd class="big">68%</dd>
        <dt>Delivery summary</dt><dd>The project overview is ready for client review. Delivery progress is 68%; the current milestone forecast is 30 Oct 2026.</dd>
        <dt>Published forecast</dt><dd>30 Oct 2026</dd>
      </dl>
      <p class="note">Shared with your client organisation. Internal comments and working drafts are excluded.</p>
    </section>"""
write("project-report-details.html", shell("Report details", "Report details", "projects", details))

# ---------------------------------------------------------------- Stakeholders
stake = f"""{project_header("stakeholders")}
    <h2 class="h-section h-section-2">Stakeholders</h2>
    <p class="lede lede-sm lede-stake">Contact your Project Manager for delivery questions and shared updates.</p>
    <article class="card person">
      <div class="person-head"><span class="person-avatar">AM</span><h3>Alex Morgan</h3><span class="role">Project Manager</span><a class="edit" href="#edit">Edit</a></div>
      <a class="mail" href="mailto:alex.morgan@boreksolutions.com">alex.morgan@boreksolutions.com</a>
      <p class="tel">Tel: -</p>
    </article>"""
write("project-stakeholders.html", shell("Stakeholders", "Account Manager", "projects", stake))

# ---------------------------------------------------------------- Profile (standalone page, no shell)
profile = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your profile · Borek Flow</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
{css}
</style>
</head>
<body class="profile-page">
<main class="profile">
  <a class="back" href="home.html">{BACK}Back</a>
  <h1 class="profile-title">Your profile</h1>
  <p class="lede lede-sm">Manage your personal details and account preferences.</p>

  <section class="card pf-head">
    <span class="pf-avatar">ME</span>
    <div><h2>Morgan Ellis</h2><p>Account Manager · Borek Solutions</p></div>
    <button type="button" class="btn btn-dark">Edit profile</button>
  </section>

  <section class="card pf-card">
    <h3 class="card-title">Personal &amp; contact information</h3>
    <p class="card-sub">Your contact details for collaborators.</p>
    <dl class="pf-grid">
      <div><dt>First name</dt><dd>Morgan</dd></div>
      <div><dt>Last name</dt><dd>Ellis</dd></div>
      <div><dt>Work email</dt><dd>morgan.ellis@boreksolutions.com</dd></div>
      <div><dt>Phone number</dt><dd>+49 30 555 0184</dd></div>
    </dl>
  </section>

  <div class="pf-two">
    <section class="card pf-card">
      <h3 class="card-title">Preferences</h3>
      <label class="field-label" for="lang">Language</label>
      <div class="select"><select id="lang"><option>English (EN)</option><option>Deutsch (DE)</option></select></div>
      <span class="field-label field-label-theme">Theme</span>
      <div class="switch-row"><span>Light mode</span><button type="button" class="switch" role="switch" aria-checked="false" aria-label="Light mode"><i></i></button></div>
    </section>
    <section class="card pf-card">
      <h3 class="card-title">Account &amp; security</h3>
      <p class="card-sub">Manage access to your Borek account.</p>
      <div class="sec-row"><span>Organisation sign-in</span><a href="#details">Details</a></div>
      <a class="signout" href="#signout">Sign out</a>
    </section>
  </div>
</main>
<script>
  document.querySelector('.switch').addEventListener('click', function () {{
    var on = this.getAttribute('aria-checked') !== 'true';
    this.setAttribute('aria-checked', on);
  }});
</script>
</body>
</html>
"""
write("profile.html", profile)
