import re
from typing import Dict, List, Set, Tuple

SYNONYM_MAP: Dict[str, Set[str]] = {
    # Cloud providers
    "aws": {"amazon web services", "amazon aws", "aws cloud"},
    "azure": {"microsoft azure", "azure cloud"},
    "gcp": {"google cloud platform", "google cloud", "gce", "gke"},
    # Container orchestration
    "kubernetes": {"k8s", "kube"},
    "openshift": {"open shift", "ocp"},
    "docker": {"docker engine", "docker compose", "docker-compose", "docker swarm"},
    "podman": set(),
    "containerd": {"cri-o"},
    "helm": set(),
    "eks": {"elastic kubernetes service", "amazon eks"},
    "aks": {"azure kubernetes service"},
    # IaC & config management
    "terraform": {"hashicorp terraform"},
    "terragrunt": set(),
    "pulumi": set(),
    "cloudformation": {"cloud formation", "cfn", "aws cloudformation"},
    "ansible": set(),
    "chef": set(),
    "puppet": set(),
    "saltstack": {"salt"},
    "crossplane": set(),
    "cdk": {"aws cdk"},
    # CI/CD
    "ci/cd": {
        "cicd",
        "ci cd",
        "continuous integration",
        "continuous delivery",
        "continuous deployment",
        "ci-cd",
    },
    "azure devops": {
        "azuredevops",
        "azure devops pipeline",
        "azure devops pipelines",
        "azure pipeline",
        "azure pipelines",
    },
    "jenkins": set(),
    "github actions": {"gh actions", "github-actions"},
    "gitlab": {
        "git lab",
        "gitlab ci",
        "gitlab-ci",
        "gitlab ci/cd",
        "gitlab cicd",
        "gitlab pipeline",
        "gitlab pipelines",
    },
    "circleci": {"circle ci"},
    "argocd": {"argo cd", "argo-cd", "argoproj"},
    "flux": {"fluxcd", "flux cd"},
    "tekton": set(),
    "spinnaker": set(),
    # Monitoring & observability
    "prometheus": {"prom"},
    "grafana": set(),
    "datadog": {"data dog"},
    "elastic": {"elasticsearch", "elk", "elk stack", "elastic stack"},
    "loki": {"grafana loki"},
    "opentelemetry": {"otel", "open telemetry"},
    "splunk": set(),
    "new relic": {"newrelic"},
    "jaeger": set(),
    "thanos": set(),
    "mimir": set(),
    "nagios": set(),
    "zabbix": set(),
    # Service mesh & networking
    "istio": set(),
    "envoy": set(),
    "linkerd": set(),
    "nginx": set(),
    "haproxy": set(),
    "traefik": set(),
    # Security & secrets
    "vault": {"hashicorp vault"},
    "consul": {"hashicorp consul"},
    # GitOps & SCM
    "gitops": {"git ops", "git-ops"},
    "git": set(),
    # Core DevOps terms
    "devops": {"dev ops", "dev-ops"},
    "sre": {
        "site reliability",
        "site reliability engineering",
        "site reliability engineer",
    },
    "platform engineer": {"platform engineering"},
    "infrastructure": {"infra"},
    "infrastructure as code": {"iac", "infra as code"},
    "cloud engineer": {"cloud engineering"},
    "linux": {"rhel", "centos", "ubuntu", "debian"},
    # Specific tools
    "argo": set(),
    "argo workflows": {"argo-workflows"},
    "kustomize": set(),
    "kafka": {"apache kafka"},
    "rabbitmq": {"rabbit mq"},
    "pagerduty": {"pager duty"},
    "opsgenie": set(),
}

# Versioned, deterministic relationships between a required concept and
# technologies that implement or provide it. These are deliberately separate
# from synonyms: AKS is not another spelling of Kubernetes, but demonstrated
# AKS usage is valid managed-Kubernetes evidence.
SEMANTIC_RELATIONSHIPS_VERSION = 1
SEMANTIC_RELATIONSHIPS: Dict[str, Dict[str, Set[str]]] = {
    "kubernetes": {
        "managed_service": {
            "aks",
            "azure kubernetes service",
            "eks",
            "amazon eks",
            "elastic kubernetes service",
            "amazon elastic kubernetes service",
            "gke",
            "google kubernetes engine",
        },
        "distribution": {
            "openshift",
            "open shift",
            "ocp",
            "rancher",
            "tanzu kubernetes grid",
        },
    },
}

USAGE_ACTION_PATTERN = re.compile(
    r"\b(?:"
    r"administer(?:ed|ing)?|architect(?:ed|ing)?|build(?:ing|s|t)?|"
    r"configur(?:e|ed|es|ing)|deploy(?:ed|ing|s)?|develop(?:ed|ing|s)?|"
    r"implement(?:ed|ing|s)?|maintain(?:ed|ing|s)?|manag(?:e|ed|es|ing)|"
    r"migrat(?:e|ed|es|ing)|monitor(?:ed|ing|s)?|operat(?:e|ed|es|ing)|"
    r"provision(?:ed|ing|s)?|scal(?:e|ed|es|ing)|secur(?:e|ed|es|ing)|"
    r"troubleshoot(?:ing|s|ed)?|upgrad(?:e|ed|es|ing)|"
    r"used?|utiliz(?:e|ed|es|ing)|work(?:ed|ing)?\s+with"
    r")\b",
    re.IGNORECASE,
)


def _build_keyword_index() -> Dict[str, str]:
    """Build reverse index: variant_lowercase -> canonical_keyword."""
    index: Dict[str, str] = {}
    for canonical, variants in SYNONYM_MAP.items():
        index[canonical.lower()] = canonical
        for v in variants:
            index[v.lower()] = canonical
    return index


KEYWORD_INDEX: Dict[str, str] = _build_keyword_index()


def normalize_tool_name(tool_name: str) -> str:
    """Collapse a tool spelling or product variant into its filter facet."""
    normalized = re.sub(r"\s+", " ", tool_name.strip().lower())
    return KEYWORD_INDEX.get(normalized, normalized).lower()

WORD_BOUNDARY_KEYWORDS: Set[str] = {
    "helm",
    "argo",
    "git",
    "flux",
    "iac",
    "tf",
    "dd",
    "sre",
    "infra",
    "elk",
    "otel",
    "cfn",
    "prom",
    "az",
    "gce",
    "gke",
    "aks",
    "eks",
    "cdk",
    "salt",
}

DEVOPS_KEYWORDS: Set[str] = set(SYNONYM_MAP.keys())


_KEYWORD_PATTERN_CACHE: Dict[str, re.Pattern] = {}
_KEYWORD_DISAMBIGUATION_SUFFIXES: Dict[str, str] = {
    "azure": r"(?!\s+(?:devops|pipelines?)\b)",
    "microsoft azure": r"(?!\s+(?:devops|pipelines?)\b)",
}


def _build_keyword_pattern(keyword: str) -> re.Pattern:
    """Build a regex pattern with word boundaries for a keyword."""
    if keyword in _KEYWORD_PATTERN_CACHE:
        return _KEYWORD_PATTERN_CACHE[keyword]
    escaped = re.escape(keyword)
    disambiguation = _KEYWORD_DISAMBIGUATION_SUFFIXES.get(keyword.lower(), "")
    pattern = re.compile(r"\b" + escaped + r"\b" + disambiguation, re.IGNORECASE)
    _KEYWORD_PATTERN_CACHE[keyword] = pattern
    return pattern


def match_keyword_in_text(
    text: str, canonical_keyword: str
) -> List[Tuple[str, re.Match]]:
    """
    Match a canonical keyword OR any of its synonyms in text.
    Returns list of (matched_variant, match_object) tuples.
    Uses word-boundary matching.
    """
    results: List[Tuple[str, re.Match]] = []

    # Try canonical form
    pattern = _build_keyword_pattern(canonical_keyword)
    for m in pattern.finditer(text):
        results.append((canonical_keyword, m))

    # Try all synonyms
    variants = SYNONYM_MAP.get(canonical_keyword.lower(), set())
    for variant in variants:
        pattern = _build_keyword_pattern(variant)
        for m in pattern.finditer(text):
            results.append((variant, m))

    return results


def normalize_heading(line: str) -> str:
    return re.sub(r"[^a-z\s]", "", line.lower()).strip()


def rejoin_hyphenated_words(text: str) -> str:
    """Rejoin words split across line breaks by a hyphen (e.g., 'Kuber-\\nnetes')."""
    return re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
