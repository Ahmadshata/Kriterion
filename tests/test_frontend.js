const fs = require("fs");

const reportPath = process.argv[2];
if (!reportPath) {
  throw new Error("usage: node tests/test_frontend.js <screening_report.html>");
}

const html = fs.readFileSync(reportPath, "utf8");
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) {
  throw new Error("generated report does not contain its dashboard script");
}
new Function(scriptMatch[1]);

const requiredFragments = [
  "function requestAmbiguityVerdict",
  "function recordFinalDecision",
  "function autoReviewAmbiguous",
  "function semanticElement",
  "function renderCreditUsage",
  "function requestInterviewPlan",
  "function renderInterviewPlan",
  "function showInterviewError",
  "function requestPassedCandidateAnalysis",
  "passedCandidateAnalysisState={}",
  "if(state.data)",
  "if(state.promise)return state.promise",
  "function updateAmbiguityCreditTotal",
  "function formatTokenCount",
  "function formatCreditCount",
  "function formatModelName",
  "node.textContent=String(text||'')",
  "fetch('/api/ai-verdict'",
  "fetch('/api/final-decision'",
  "fetch('/api/passed-candidate-analysis'",
  "AI verdict",
  "No citation applicable",
  "Interview Architect",
  "Analyze issues &amp; build questions",
  "Ambiguous evidence",
  "Strong claims",
  "Timeline overlaps",
  "Career gaps",
  "Timeline signals",
  "Detected issue",
  "Single interview question",
  "No defensible CV signal found — no question generated.",
  'class="interview-architect-container"',
  'class="interview-architect-btn"',
  ".interview-groups{display:grid;grid-template-columns:1fr;gap:.7rem;align-items:start}",
  ".interview-question{padding:1rem;",
  ".interview-source-label{display:block;margin-top:1rem;margin-bottom:.3rem;",
  ".interview-listen{margin-top:.9rem;padding:.68rem .75rem;",
  "CV evidence anchor",
  "Listen for: ",
  "Final decision: Pass candidate",
  "Final decision: Fail candidate",
  "pill.textContent='FINAL '+decision",
  "Work experience only",
  "quotation verified against parsed work experience",
  'class="candidate-review"',
  'class="review-hero ',
  'class="decision-rationale ',
  'class="keyword-grid"',
  'class="kw-tool-icon"',
  'src="tools/aws.png"',
  'class="kw-citation-head"',
  'class="kw-citation-source"',
  ".keyword-grid{display:flex;flex-direction:column;gap:1rem}",
  '[data-theme="dark"] .tool-icon-dark{display:block!important}',
  '[data-theme="light"] .tool-icon-light{display:block!important}',
  ".tool-filter-chip img.tool-icon-enlarged{width:24px;height:24px;object-fit:fill}",
  ".tool-filter-chip img.tool-icon-docker{width:28px;height:16px;object-fit:contain}",
  ".kw-tool-icon img.tool-icon-enlarged{width:38px;height:38px;object-fit:fill}",
  ".kw-tool-icon img.tool-icon-docker{width:38px;height:22px;object-fit:contain}",
  ".kw-tool-icon img.tool-icon-zabbix{transform:scaleY(1.65)}",
  'class="review-split"',
  "function toggleCandidateReview",
  "function applyCandidateFilters",
  "selectedToolFilters=new Set()",
  "Array.from(selectedToolFilters).every",
  'class="tool-filter-panel"',
  'class="tool-filter-chip"',
  'id="toolFilterClear"',
  'id="toolFilterSummary"',
  "with all: ",
  'id="criterionLab"',
  'id="criterionYears"',
  'data-mode="required"',
  'data-mode="preferred"',
  'data-mode="off"',
  'id="criterionLabData"',
  "function criterionLabClassify",
  "function criterionLabEvaluate",
  "function updateCriterionLab",
  "function criterionLabApplyResults",
  "function criterionLabUpdateDashboard",
  'id="criterionApply"',
  "Apply to CV results",
  "profile YAML unchanged",
  'class="lab-application-note"',
  "Report only",
  "Rule impact",
  "Candidate movement",
  "Profile signals",
  "Kriterion Lab uses the report’s verified experience evidence",
  'id="evidenceXray"',
  'id="evidenceXrayData"',
  'class="xray-open-btn"',
  "Inspect source",
  'id="xrayPageImage"',
  "function openEvidenceXray",
  "function closeEvidenceXray",
  "function renderEvidenceXray",
  "function renderXrayExcerpt",
  "function navigateEvidenceXray",
  "function loadXrayPagePreview",
  "function xrayPreviewUrl",
  "evidenceXrayIndicesByCandidate",
  "&search=",
  ".xray-excerpt mark{padding:1px 3px;border-radius:3px;background:#facc15",
  "Exact extracted evidence",
  "Open cited page in a new tab",
  "detail.style.display='table-row'",
  "btn.textContent='Try again'",
  "AI verdict unavailable",
  'class="section-icon section-icon-codex" aria-hidden="true">CX</div>',
  ".section-icon-codex{width:38px;height:38px;",
  'var aiProvider="codex";',
  'var aiProviderName="Codex";',
  "var showAiUsage=false;",
  ".section-icon-ai{width:40px;height:40px;border-radius:0;background:transparent;color:var(--amber)}",
  ".section-icon-ai .copilot-icon{display:block;width:38px;height:38px;object-fit:contain}",
  'class="exp-connector"',
  'class="exp-particle"',
  "animation:exp-flow-up 4.2s linear infinite",
  "@keyframes exp-flow-up",
  "height:calc(100% + var(--exp-gap))",
  'class="stat-box stat-all stat-active screening-intake"',
  'class="outcome-grid"',
  'class="outcome-bar"',
  'class="donut-segment"',
  'class="outcome-distribution"',
  "@keyframes outcome-bar-down",
  "@keyframes distribution-in",
  "@keyframes donut-draw",
  "box.setAttribute('aria-pressed','true')",
  'class="logo-text">Kriterion</div>',
  "@keyframes brand-mark-in",
  "@keyframes brand-name-in",
  'class="restrictions"',
  "Required in Experience",
  "Minimum Experience",
  'class="chip chip-rule"',
  'class="insights-stage"',
  'class="charts-column"',
  'class="podium-column"',
  'class="chart-card chart-reasons"',
  'class="chart-card chart-coverage"',
  'class="demo-cv"',
  'class="demo-scan-beam"',
  'class="demo-verdict-orb"',
  'class="demo-podium"',
  'class="demo-outcomes"',
  "function renderScreeningDemo",
  "--demo-scan",
  "--demo-reasons",
  "--demo-coverage",
  "--demo-morph",
  "--demo-flight-x",
  "--demo-tilt-y",
  "--demo-depth",
  "--demo-pass-glow",
  "--demo-fail-glow",
  "--demo-amb-glow",
  "height:350vh",
  "screeningTargetOffset",
  "Profile-driven animation · aggregate values are from this report",
  "AI-assisted review",
  "AI helps Kriterion resolve ambiguous evidence",
  "Credit usage unavailable",
  "Copilot did not return exact AI credit metadata for this review.",
  "GitHub AI Credits",
  "modelLabel+' • '+formatCreditCount(credits)",
];
for (const fragment of requiredFragments) {
  if (!html.includes(fragment)) {
    throw new Error(`missing ambiguity AI verdict frontend fragment: ${fragment}`);
  }
}

const forbiddenFragments = [
  "requestVerdict",
  "recordSemanticDecision",
  "fetch('/api/semantic-decision'",
  "Approve interpretation",
  "Reject interpretation",
  "submitChat",
  "fetch('/api/verdict'",
  "fetch('/api/chat'",
  'class="detail-tabs"',
  'class="tab-content',
  "data-tab=",
  'class="detail-content"',
  'class="drawer-shell"',
  'class="candidate-drawer"',
  "function openCandidateDrawer",
  "function closeCandidateDrawer",
  'class="stats-row"',
  'class="meta-line"',
  'class="charts-section"',
  'class="screen-demo"',
  "Alex Morgan",
  "Senior Product Designer",
  "Scroll to see an abstract CV checked against the active profile.",
  "--demo-exit",
  "--exit-x",
  "grid-template-columns:repeat(3,minmax(0,1fr));gap:.6rem",
  "max-height:96px",
  "Exact token counts appear after ambiguous CV recommendations are generated or loaded.",
  "Copilot did not return exact token metadata for this review.",
  "renderEvidenceXray(evidenceXrayCurrentIndex-1)",
  "renderEvidenceXray(evidenceXrayCurrentIndex+1)",
  'id="aiUsageOverview"',
  '<img class="copilot-icon" src="GitHub-Copilot-Blink.gif"',
  "AI recommendation",
  "AI Profile Critic",
  'class="candidate-intelligence-container"',
  'class="candidate-intelligence-btn"',
];
for (const fragment of forbiddenFragments) {
  if (html.includes(fragment)) {
    throw new Error(`obsolete AI workflow frontend remains: ${fragment}`);
  }
}

const failureChartIndex = html.indexOf("<h3>Top Failure Reasons</h3>");
const coverageChartIndex = html.indexOf("<h3>Keyword Coverage</h3>");
if (
  failureChartIndex === -1 ||
  coverageChartIndex === -1 ||
  failureChartIndex >= coverageChartIndex
) {
  throw new Error(
    "Top Failure Reasons must appear above Keyword Coverage in the left insight column",
  );
}

const cvTableIndex = html.indexOf('<tbody id="tableBody">');
const criterionLabIndex = html.indexOf('id="criterionLab"');
const aiAssistedReviewIndex = html.indexOf("AI helps Kriterion resolve ambiguous evidence");
if (
  cvTableIndex === -1 ||
  criterionLabIndex === -1 ||
  aiAssistedReviewIndex === -1 ||
  cvTableIndex >= criterionLabIndex ||
  cvTableIndex >= aiAssistedReviewIndex
) {
  throw new Error(
    "The CV results table must appear before Kriterion Lab and AI-assisted review",
  );
}

const aiReviewSectionCount = (
  html.match(/class="review-section ai-review-section"/g) || []
).length;
const ambiguousCandidateCount = (
  html.match(/class="data-row row-ambiguous"/g) || []
).length;
if (
  aiReviewSectionCount !== ambiguousCandidateCount ||
  aiReviewSectionCount === 0
) {
  throw new Error(
    `AI review sections (${aiReviewSectionCount}) must match ambiguous candidates (${ambiguousCandidateCount})`,
  );
}

const interviewArchitectCount = (
  html.match(/class="interview-architect-container"/g) || []
).length;
const passedCandidateCount = (
  html.match(/class="data-row row-pass"/g) || []
).length;
if (interviewArchitectCount !== passedCandidateCount || interviewArchitectCount === 0) {
  throw new Error(
    `Merged Interview Architect sections (${interviewArchitectCount}) must match passed candidates (${passedCandidateCount})`,
  );
}

const experienceConnectorCount = (
  html.match(/class="exp-connector"/g) || []
).length;
const experienceParticleCount = (
  html.match(/class="exp-particle"/g) || []
).length;
if (
  experienceConnectorCount === 0 ||
  experienceParticleCount !== experienceConnectorCount * 3
) {
  throw new Error(
    `experience connectors (${experienceConnectorCount}) must each contain three particles (${experienceParticleCount})`,
  );
}

const xrayDataMatch = html.match(
  /<script type="application\/json" id="evidenceXrayData">([\s\S]*?)<\/script>/,
);
if (!xrayDataMatch) {
  throw new Error("generated report does not contain Evidence X-Ray data");
}
const xrayItems = JSON.parse(xrayDataMatch[1]);
const xrayButtonCount = (html.match(/class="xray-open-btn"/g) || []).length;
const xrayHeaderButtonCount = (
  html.match(
    /class="kw-citation-source"><span class="kw-relation">[\s\S]*?<\/span><button type="button" class="xray-open-btn"/g,
  ) || []
).length;
if (xrayItems.length === 0 || xrayButtonCount !== xrayItems.length) {
  throw new Error(
    `Evidence X-Ray items (${xrayItems.length}) must match source buttons (${xrayButtonCount})`,
  );
}
if (xrayHeaderButtonCount !== xrayButtonCount) {
  throw new Error(
    `Evidence X-Ray buttons in citation headers (${xrayHeaderButtonCount}) must match all source buttons (${xrayButtonCount})`,
  );
}

console.log("automatic ambiguity AI verdict frontend check passed");
