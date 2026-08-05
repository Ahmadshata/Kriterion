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
  "node.textContent=String(text||'')",
  "fetch('/api/ai-verdict'",
  "fetch('/api/final-decision'",
  "AI recommendation",
  "Final decision: Pass candidate",
  "Final decision: Fail candidate",
  "pill.textContent='FINAL '+decision",
  "Work experience only",
  "quotation verified against parsed work experience",
  'class="candidate-review"',
  'class="review-hero ',
  'class="decision-rationale ',
  'class="keyword-grid"',
  'class="review-split"',
  "function toggleCandidateReview",
  "detail.style.display='table-row'",
  "btn.textContent='Try again'",
  "Recommendation unavailable",
  'class="copilot-icon"',
  'class="exp-connector"',
  'class="exp-particle"',
  "animation:exp-flow-down 4.2s linear infinite",
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

console.log("automatic ambiguity AI verdict frontend check passed");
