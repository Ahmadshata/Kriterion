---
name: create-profile
description: Create or update a Kriterion YAML screening profile with employment-history requirements and deterministic filters. Use when asked to create a profile, define a role, or configure candidate screening.
---

## Goal

Create a valid Kriterion profile. Default to `./profiles/profile.yaml`; use another path only when the user requests one.

## Gather requirements

Ask one or two focused questions at a time. Do not ask for values the user already supplied.

1. Role name and minimum years of relevant experience.
2. Two to five technologies that must be demonstrated in employment history.
3. Whether freelance/self-employed work should count as employment experience.
   Explain that `false` excludes those entries from both required-technology
   evidence and years of experience; do not silently choose for the user.
4. Optional minimum score.
5. Training programs whose duration must not count as professional experience.
6. Optional required programs, excluded companies, and excluded universities.
7. Optional scoring weights; use defaults unless customization is requested.

Explain that `must_have_in_experience` excludes skills lists, certifications, courses, projects, and education. A candidate who lists a technology outside employment history does not satisfy that requirement.

## Defaults

- Output path: `./profiles/profile.yaml`
- `min_score`: `null`
- `include_freelance_experience`: ask the user; use `true` only when they decline to choose
- Education programs: `iti`, `nti`, `sprints`, `depi`, `alx`, `information technology institute`, `national technology institute`, `digital egypt pioneers initiative`
- `preferred_programs`, `excluded_companies`, `excluded_universities`: `null`
- Scoring: `keywords_found=30`, `devops_years=30`, `recency=20`, `keyword_depth=10`, `no_ambiguity=10`

## Generate

Use lowercase must-have technologies. Show the final YAML before writing it.

```yaml
role: {role_name}

min_experience_years: {number}

include_freelance_experience: {true_or_false}

must_have_in_experience:
  - {keyword1}
  - {keyword2}

min_score: null

education_programs:
  - iti
  - nti
  - sprints
  - depi
  - alx
  - information technology institute
  - national technology institute
  - digital egypt pioneers initiative

preferred_programs: null
excluded_companies: null
excluded_universities: null

# scoring_weights:
#   keywords_found: 30
#   devops_years: 30
#   recency: 20
#   keyword_depth: 10
#   no_ambiguity: 10
```

Only add custom scoring weights when requested, and ensure they sum to 100.

## Screening semantics

- Synonyms are deterministic; for example, `kubernetes` recognizes `k8s` and `kube`, and `aws` recognizes `amazon web services`.
- Approved Kubernetes relationships include AKS, EKS, GKE, OpenShift, Rancher, and Tanzu Kubernetes Grid.
- Demonstrated usage of a related platform can qualify deterministically; a weak related mention becomes AMBIGUOUS.
- AI handles only unresolved ambiguity using parsed work-experience evidence. It cannot override deterministic missing requirements.
- When `include_freelance_experience` is `false`, freelance/self-employed entries
  supply neither experience years nor must-have technology evidence.

## Finish

After writing the profile, give the matching command:

- Default profile: `./kriterion.sh`
- Custom profile: `./kriterion.sh --profile "{profile_path}"`

Do not run installation or screening unless the user also asks for it.
