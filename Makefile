SHELL := /bin/bash
.DEFAULT_GOAL := help

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CONFIG := $(ROOT)/config.yaml
GENERATED := $(ROOT)/.generated
STAMPS := $(ROOT)/.state/stamps
LOGS := $(ROOT)/logs
YQ ?= yq
UV ?= uv
UV_RUN := $(UV) run --directory $(ROOT)
# Empty when yq is not on PATH so `make setup` / `make help` work on a bare host.
yq_read = $(shell command -v $(YQ) >/dev/null 2>&1 && $(YQ) -r $(1) $(CONFIG))

# One directory per invocation, with logs/latest pointing at the newest run.
RUN_ID ?= $(shell date +%Y%m%d-%H%M%S)
LOG_DIR := $(LOGS)/$(RUN_ID)

# Each recipe streams to the console and appends to logs/<run-id>/<step>.log.
# GNU Make 3.81 (macOS) has no .SHELLFLAGS, so pipefail is set per recipe line.
LOGGED = set -o pipefail; mkdir -p $(LOG_DIR); ln -sfn $(LOG_DIR) $(LOGS)/latest;
TEE_TO = 2>&1 | tee -a $(LOG_DIR)

KIND_NAME := $(call yq_read,'.kind.name')
KUBE_CONTEXT := kind-$(KIND_NAME)
REC_NAMESPACE := $(call yq_read,'.redisEnterpriseCluster.namespace')
REC_NAME := $(call yq_read,'.redisEnterpriseCluster.name')
OPERATOR_VERSION := $(call yq_read,'.versions.redisEnterpriseOperatorChart')
LC_VERSION := $(call yq_read,'.versions.langcacheChart')
RAM_VERSION := $(call yq_read,'.versions.ramChart')
CR_VERSION := $(call yq_read,'.versions.contextRetrieverChart')
INSIGHT_IMAGE := $(call yq_read,'.versions.redisInsightImage')
NGINX_IMAGE := $(call yq_read,'.versions.nginxImage')
WORKSHOP_WEB_IMAGE := $(call yq_read,'.versions.workshopWebImage')
WORKSHOP_VSCODE_IMAGE := $(call yq_read,'.versions.workshopVscodeImage')
INSIGHT_NAMESPACE := $(call yq_read,'.insight.namespace')
INSIGHT_PORT := $(call yq_read,'.insight.port')
WORKSHOP_NAMESPACE := $(call yq_read,'.workshop.namespace')
WORKSHOP_HOST_PORT := $(call yq_read,'.workshop.hostPort')
PACK ?= $(call yq_read,'.workshop.pack')
RE_LICENSE := $(ROOT)/$(call yq_read,'.licenses.redisEnterprise')
RAM_LICENSE := $(ROOT)/$(call yq_read,'.licenses.ram')
LC_LICENSE := $(ROOT)/$(call yq_read,'.licenses.langcache')
CR_LICENSE := $(ROOT)/$(call yq_read,'.licenses.contextRetriever')
OPENAI_KEY := $(ROOT)/$(call yq_read,'.inference.openAIKeyFile')
LC_NAMESPACE := $(call yq_read,'.iris.namespaces.langcache')
RAM_NAMESPACE := $(call yq_read,'.iris.namespaces.ram')
CR_NAMESPACE := $(call yq_read,'.iris.namespaces.contextRetriever')
DATABASE_NAMES := $(call yq_read,'.databases | keys | .[]')

# Only files that exist can be prerequisites. Adding a license later makes the
# dependent step out of date, so it re-runs on the next invocation.
SECRET_FILES := $(wildcard $(RAM_LICENSE) $(LC_LICENSE) $(CR_LICENSE) $(OPENAI_KEY))

GENERATED_FILES := $(GENERATED)/kind.yaml $(GENERATED)/operator-values.yaml \
	$(GENERATED)/rec.yaml $(GENERATED)/redbs.yaml \
	$(GENERATED)/values/langcache.yaml $(GENERATED)/values/ram.yaml \
	$(GENERATED)/values/context-retriever.yaml

.PHONY: help setup validate render pin-latest cluster repos operator license rec
.PHONY: databases secrets iris all status chart-validate destroy logs redo
.PHONY: ram-store ram-mcp test-ram-core test-ram-features test-ram insight
.PHONY: langcache-cache test-langcache-core test-langcache-features test-langcache
.PHONY: cr-surface test-cr-core test-cr-features test-cr workshop

help: ## Show available targets.
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install curl, git, jq, yq, uv, helm, kubectl, kind, and vim (macOS / Ubuntu 20.04+).
	@bash $(ROOT)/scripts/setup.sh

# ---------------------------------------------------------------------------
# Steps record completion under .state/stamps. A step re-runs only when one of
# its inputs is newer than its stamp, so a second `make all` is a no-op instead
# of replaying the whole cluster build.
# ---------------------------------------------------------------------------

$(STAMPS):
	@mkdir -p $@

$(STAMPS)/deps: $(ROOT)/pyproject.toml $(ROOT)/uv.lock | $(STAMPS)
	@$(LOGGED) $(UV) --directory $(ROOT) sync --locked $(TEE_TO)/deps.log
	@touch $@

$(STAMPS)/render: $(CONFIG) $(ROOT)/scripts/render.py $(STAMPS)/deps | $(STAMPS)
	@$(LOGGED) $(UV_RUN) python scripts/render.py render $(TEE_TO)/render.log
	@touch $@

# render.py rewrites a file only when its content changes, so an unchanged
# manifest keeps its mtime and does not invalidate the steps below.
$(GENERATED_FILES): $(STAMPS)/render ;

$(STAMPS)/cluster: $(GENERATED)/kind.yaml $(ROOT)/scripts/tune_cluster.py | $(STAMPS)
	@$(LOGGED) if kubectl --context $(KUBE_CONTEXT) get nodes >/dev/null 2>&1; then \
		echo "kubectl already reaches $(KUBE_CONTEXT); skipping kind create"; \
	elif kind get clusters | awk '$$0 == "$(KIND_NAME)" {found=1} END {exit !found}'; then \
		echo "Kind cluster $(KIND_NAME) exists; exporting kubeconfig"; \
		kind export kubeconfig --name $(KIND_NAME); \
	else \
		kind create cluster --config $(GENERATED)/kind.yaml; \
	fi $(TEE_TO)/cluster.log
	@$(LOGGED) $(UV_RUN) python scripts/tune_cluster.py $(TEE_TO)/cluster.log
	@touch $@

# Refreshing the Helm index says nothing about whether an installed release is
# stale, so downstream steps take this order-only: it must have run, but a
# newer index does not by itself force a reinstall. Use `make redo STEP=repos`.
$(STAMPS)/repos: | $(STAMPS)
	@$(LOGGED) helm repo add redis https://helm.redis.io --force-update $(TEE_TO)/repos.log
	@$(LOGGED) helm repo add redis-ai https://helm.redis.io/ai --force-update $(TEE_TO)/repos.log
	@$(LOGGED) helm repo update redis redis-ai $(TEE_TO)/repos.log
	@touch $@

$(STAMPS)/operator: $(STAMPS)/cluster $(GENERATED)/operator-values.yaml | $(STAMPS) $(STAMPS)/repos
	@$(LOGGED) kubectl config use-context $(KUBE_CONTEXT) $(TEE_TO)/operator.log
	@$(LOGGED) helm upgrade --install redis-enterprise-operator \
		redis/redis-enterprise-operator \
		--version $(OPERATOR_VERSION) \
		--namespace $(REC_NAMESPACE) \
		--create-namespace \
		-f $(GENERATED)/operator-values.yaml \
		--wait --timeout 10m $(TEE_TO)/operator.log
	@$(LOGGED) kubectl wait --for=condition=Established \
		crd/redisenterpriseclusters.app.redislabs.com \
		crd/redisenterprisedatabases.app.redislabs.com \
		--timeout=5m $(TEE_TO)/operator.log
	@touch $@

$(STAMPS)/license: $(STAMPS)/operator $(RE_LICENSE) | $(STAMPS)
	@test -s "$(RE_LICENSE)" || \
		(echo "Missing Redis Enterprise license: $(RE_LICENSE)" >&2; exit 1)
	@$(LOGGED) kubectl -n $(REC_NAMESPACE) create secret generic rec-license \
		--from-file=license="$(RE_LICENSE)" \
		--dry-run=client -o yaml | kubectl apply -f - $(TEE_TO)/license.log
	@touch $@

$(STAMPS)/rec: $(STAMPS)/license $(GENERATED)/rec.yaml | $(STAMPS)
	@$(LOGGED) kubectl apply -f $(GENERATED)/rec.yaml $(TEE_TO)/rec.log
	@$(LOGGED) $(UV_RUN) python scripts/wait.py rec $(REC_NAME) \
		--namespace $(REC_NAMESPACE) --timeout 1800 $(TEE_TO)/rec.log
	@$(LOGGED) $(UV_RUN) python scripts/check_license.py \
		--namespace $(REC_NAMESPACE) --name $(REC_NAME) accepted $(TEE_TO)/rec.log
	@touch $@

$(STAMPS)/databases: $(STAMPS)/rec $(GENERATED)/redbs.yaml | $(STAMPS)
	@$(LOGGED) $(UV_RUN) python scripts/check_license.py \
		--namespace $(REC_NAMESPACE) --name $(REC_NAME) capacity \
		--required $(words $(DATABASE_NAMES)) $(TEE_TO)/databases.log
	@$(LOGGED) kubectl apply -f $(GENERATED)/redbs.yaml $(TEE_TO)/databases.log
	@$(LOGGED) $(UV_RUN) python scripts/wait.py redb $(DATABASE_NAMES) \
		--namespace $(REC_NAMESPACE) --timeout 1800 $(TEE_TO)/databases.log
	@touch $@

$(STAMPS)/secrets: $(STAMPS)/databases $(ROOT)/scripts/materialize_secrets.py \
		$(SECRET_FILES) | $(STAMPS)
	@$(LOGGED) $(UV_RUN) python scripts/materialize_secrets.py $(TEE_TO)/secrets.log
	@touch $@

$(STAMPS)/insight: $(STAMPS)/secrets $(ROOT)/scripts/insight.py $(CONFIG) | $(STAMPS)
	@$(LOGGED) docker pull $(INSIGHT_IMAGE) $(TEE_TO)/insight.log
	@$(LOGGED) kind load docker-image $(INSIGHT_IMAGE) --name $(KIND_NAME) $(TEE_TO)/insight.log
	@$(LOGGED) $(UV_RUN) python scripts/insight.py $(TEE_TO)/insight.log
	@touch $@

# Each product installs only when its license file is present. The stamp is
# still recorded when skipped, so adding the license later re-triggers it.
$(STAMPS)/iris-langcache: $(STAMPS)/secrets $(GENERATED)/values/langcache.yaml \
		$(wildcard $(LC_LICENSE)) | $(STAMPS)
	@$(LOGGED) if [ -s "$(LC_LICENSE)" ]; then \
		helm upgrade --install langcache redis-ai/langcache \
			--version $(LC_VERSION) --namespace $(LC_NAMESPACE) \
			-f $(GENERATED)/values/langcache.yaml \
			--wait --timeout 15m; \
	else \
		echo "skipping LangCache: missing $(LC_LICENSE)"; \
	fi $(TEE_TO)/iris-langcache.log
	@touch $@

$(STAMPS)/langcache-cache: $(STAMPS)/iris-langcache $(ROOT)/scripts/langcache_api.py | $(STAMPS)
	@$(LOGGED) if [ -s "$(LC_LICENSE)" ]; then \
		$(UV_RUN) python scripts/langcache_api.py; \
	else \
		echo "skipping LangCache default cache: missing $(LC_LICENSE)"; \
	fi $(TEE_TO)/langcache-cache.log
	@touch $@

$(STAMPS)/iris-ram: $(STAMPS)/secrets $(GENERATED)/values/ram.yaml \
		$(wildcard $(RAM_LICENSE)) | $(STAMPS)
	@$(LOGGED) if [ -s "$(RAM_LICENSE)" ]; then \
		helm upgrade --install ram redis-ai/redis-agent-memory \
			--version $(RAM_VERSION) --namespace $(RAM_NAMESPACE) \
			-f $(GENERATED)/values/ram.yaml \
			--wait --timeout 15m; \
	else \
		echo "skipping Agent Memory: missing $(RAM_LICENSE)"; \
	fi $(TEE_TO)/iris-ram.log
	@touch $@

$(STAMPS)/iris-context-retriever: $(STAMPS)/secrets \
		$(GENERATED)/values/context-retriever.yaml \
		$(wildcard $(CR_LICENSE)) | $(STAMPS)
	@$(LOGGED) if [ -s "$(CR_LICENSE)" ]; then \
		helm upgrade --install context-retriever redis-ai/redis-context-retriever \
			--version $(CR_VERSION) --namespace $(CR_NAMESPACE) \
			-f $(GENERATED)/values/context-retriever.yaml \
			--wait --timeout 15m; \
	else \
		echo "skipping Context Retriever: missing $(CR_LICENSE)"; \
	fi $(TEE_TO)/iris-context-retriever.log
	@touch $@

$(STAMPS)/ram-store: $(STAMPS)/iris-ram $(ROOT)/scripts/ram_api.py | $(STAMPS)
	@$(LOGGED) $(UV_RUN) python scripts/ram_api.py $(TEE_TO)/ram-store.log
	@touch $@

$(STAMPS)/cr-surface: $(STAMPS)/iris-context-retriever \
		$(ROOT)/scripts/cr_api.py | $(STAMPS)
	@$(LOGGED) if [ -s "$(CR_LICENSE)" ]; then \
		$(UV_RUN) python scripts/cr_api.py; \
	else \
		echo "skipping Context Retriever default surface: missing $(CR_LICENSE)"; \
	fi $(TEE_TO)/cr-surface.log
	@touch $@

$(STAMPS)/workshop: $(STAMPS)/insight $(STAMPS)/langcache-cache $(STAMPS)/ram-store \
		$(STAMPS)/cr-surface \
		$(ROOT)/scripts/workshop.py $(ROOT)/scripts/agentic_provision.py \
		$(ROOT)/scripts/ram_mcp.py \
		$(ROOT)/scripts/langcache_mcp.py $(ROOT)/scripts/cr_mcp.py \
		$(CONFIG) \
		$(shell find $(ROOT)/workshop -type f \
			! -path '*/node_modules/*' ! -path '*/dist/*') | $(STAMPS)
	@$(LOGGED) docker pull $(NGINX_IMAGE) $(TEE_TO)/workshop.log
	@$(LOGGED) docker build -f $(ROOT)/workshop/docker/web/Dockerfile \
		-t $(WORKSHOP_WEB_IMAGE) $(ROOT) $(TEE_TO)/workshop.log
	@$(LOGGED) docker build -f $(ROOT)/workshop/docker/vscode/Dockerfile \
		-t $(WORKSHOP_VSCODE_IMAGE) $(ROOT) $(TEE_TO)/workshop.log
	@$(LOGGED) kind load docker-image $(NGINX_IMAGE) --name $(KIND_NAME) $(TEE_TO)/workshop.log
	@$(LOGGED) kind load docker-image $(WORKSHOP_WEB_IMAGE) --name $(KIND_NAME) $(TEE_TO)/workshop.log
	@$(LOGGED) kind load docker-image $(WORKSHOP_VSCODE_IMAGE) --name $(KIND_NAME) $(TEE_TO)/workshop.log
	@$(LOGGED) $(UV_RUN) python scripts/workshop.py --pack "$(PACK)" $(TEE_TO)/workshop.log
	@touch $@

workshop: $(STAMPS)/workshop ## Install the workbench for workshop.pack (override with PACK=agentic).
	@echo "Open the workbench (no port-forward):"
	@echo "  http://127.0.0.1:$(WORKSHOP_HOST_PORT)/"
	@echo "  (on a remote/lab VM behind a reverse proxy, use that proxy's URL for this port/host instead of 127.0.0.1)"
	@echo "VS Code in the workbench is the participant IDE (Continue + Iris MCP)."
	@echo "Switch packs with: make redo STEP=workshop && make workshop PACK=agentic"

# ---------------------------------------------------------------------------
# Friendly names for the steps above.
# ---------------------------------------------------------------------------

render: $(STAMPS)/render ## Render Kind, REC, REDB, and Iris values under .generated/.
cluster: $(STAMPS)/cluster ## Create/tune the 1-control-plane + 3-worker Kind cluster.
repos: $(STAMPS)/repos ## Add/update public Redis Operator and Redis AI Helm repositories.
operator: $(STAMPS)/operator ## Install the pinned Redis Enterprise Operator chart.
license: $(STAMPS)/license ## Create/update the REC license Secret.
rec: $(STAMPS)/rec ## Create the 3-node REC and verify the license was accepted.
databases: $(STAMPS)/databases ## Create the dedicated REDBs and wait until Active.
secrets: $(STAMPS)/secrets ## Materialize Redis URLs and product license/provider Secrets.
insight: $(STAMPS)/insight ## Install Redis Insight with every REDB preconfigured.
	@echo "Open Redis Insight (no port-forward; the workbench publishes it):"
	@echo "  http://127.0.0.1:$(WORKSHOP_HOST_PORT)/redisinsight/"
	@echo "  (on a remote/lab VM behind a reverse proxy, use that proxy's URL for this port/host instead of 127.0.0.1)"
ram-store: $(STAMPS)/ram-store ## Provision the default Agent Memory store and MCP URL.
langcache-cache: $(STAMPS)/langcache-cache ## Provision the default LangCache cache and API key.
cr-surface: $(STAMPS)/cr-surface ## Provision the default Context Retriever surface, seed data, and agent key.
ram-mcp: $(STAMPS)/ram-store ## Print the host-side Agent Memory MCP command (maintainers only).
	@echo "Maintainer MCP on this laptop; workshop participants use Continue in workbench VS Code."
	@echo "Add this once to .cursor/mcp.json; Kind recreates do not change it:"
	@echo
	@printf '%s\n' '  "redis-agent-memory": {' \
	  '    "command": "uv",' \
	  '    "args": ["run", "--directory", "$(ROOT)", "python", "scripts/ram_mcp.py"]' \
	  '  }'

iris: $(STAMPS)/langcache-cache $(STAMPS)/ram-store $(STAMPS)/cr-surface ## Install public Iris charts whose license files are present.
	@echo "Playbook is skipped: no public redis-ai/redis-playbook chart is published."

all: iris insight workshop ## Create Kind, Redis Enterprise/REDBs, Iris, Insight, and the workbench.

test-ram-core: $(STAMPS)/ram-store ## Run deterministic Agent Memory public-API tests.
	@$(LOGGED) $(UV_RUN) pytest -v -m "not openai and not llm" \
		tests/test_core.py tests/test_mcp.py tests/test_extraction.py \
		tests/test_insight.py tests/test_workshop.py $(TEE_TO)/test-ram-core.log

test-ram-features: $(STAMPS)/ram-store ## Run OpenAI-backed LTM, MCP, extraction, and redaction tests.
	@$(LOGGED) $(UV_RUN) pytest -v -m "openai or llm" \
		tests/test_core.py tests/test_mcp.py tests/test_extraction.py \
		$(TEE_TO)/test-ram-features.log

test-ram: test-ram-core test-ram-features ## Run the complete Agent Memory Kind suite.

test-langcache-core: $(STAMPS)/langcache-cache ## Run deterministic LangCache public-API tests.
	@$(LOGGED) $(UV_RUN) pytest -v -m "not openai and not llm" \
		tests/test_langcache_core.py tests/test_langcache_features.py \
		tests/test_langcache_mcp.py tests/test_workshop.py \
		$(TEE_TO)/test-langcache-core.log

test-langcache-features: $(STAMPS)/langcache-cache ## Run OpenAI-backed LangCache set/search/TTL tests.
	@$(LOGGED) $(UV_RUN) pytest -v -m "openai or llm" \
		tests/test_langcache_core.py tests/test_langcache_features.py \
		$(TEE_TO)/test-langcache-features.log

test-langcache: test-langcache-core test-langcache-features ## Run the complete LangCache Kind suite.

test-cr-core: $(STAMPS)/cr-surface ## Run deterministic Context Retriever public-API tests.
	@$(LOGGED) $(UV_RUN) pytest -v -m "not openai and not llm" \
		tests/test_cr_core.py tests/test_cr_features.py tests/test_workshop.py \
		$(TEE_TO)/test-cr-core.log

test-cr-features: $(STAMPS)/cr-surface ## Run OpenAI-backed Context Retriever MCP search tests.
	@$(LOGGED) $(UV_RUN) pytest -v -m "openai or llm" \
		tests/test_cr_core.py tests/test_cr_features.py \
		$(TEE_TO)/test-cr-features.log

test-cr: test-cr-core test-cr-features ## Run the complete Context Retriever Kind suite.

validate: $(STAMPS)/deps ## Validate config and tooling without changing the cluster.
	@$(UV_RUN) python scripts/render.py validate
	@$(UV_RUN) python -m py_compile scripts/*.py
	@for tool in curl git jq docker kind kubectl helm $(YQ) $(UV); do \
		command -v $$tool >/dev/null || { echo "missing tool: $$tool" >&2; exit 1; }; \
	done
	@echo "tooling is available"

pin-latest: $(STAMPS)/deps ## Update config.yaml to the newest public chart versions.
	@$(UV_RUN) python scripts/pin_latest.py

chart-validate: $(STAMPS)/render | $(STAMPS)/repos ## Render public Iris charts locally without installing.
	@helm template langcache redis-ai/langcache --version $(LC_VERSION) \
		--namespace $(LC_NAMESPACE) -f $(GENERATED)/values/langcache.yaml >/dev/null
	@helm template ram redis-ai/redis-agent-memory --version $(RAM_VERSION) \
		--namespace $(RAM_NAMESPACE) -f $(GENERATED)/values/ram.yaml >/dev/null
	@helm template context-retriever redis-ai/redis-context-retriever \
		--version $(CR_VERSION) --namespace $(CR_NAMESPACE) \
		-f $(GENERATED)/values/context-retriever.yaml >/dev/null
	@echo "all public Iris charts render with generated values"

# ---------------------------------------------------------------------------
# Inspection and teardown.
# ---------------------------------------------------------------------------

status: ## Show completed steps, Kind nodes, REC/REDBs, pods, and Helm releases.
	@echo "completed steps:"
	@ls -1 $(STAMPS) 2>/dev/null | sed 's/^/  /' || echo "  (none)"
	@echo
	@kubectl config use-context $(KUBE_CONTEXT) >/dev/null
	@kubectl get nodes -o wide
	@kubectl -n $(REC_NAMESPACE) get rec,redb,pods
	@kubectl get pods -A
	@helm list -A

logs: ## Show the log directory for the most recent run.
	@test -d $(LOGS)/latest || { echo "no runs recorded yet"; exit 0; }
	@echo "$$(readlink $(LOGS)/latest)"
	@ls -1 $(LOGS)/latest | sed 's/^/  /'

redo: ## Forget one or more steps so they re-run: make redo STEP="rec databases".
	@test -n "$(STEP)" || { echo "usage: make redo STEP=\"rec databases\"" >&2; exit 1; }
	@for s in $(STEP); do rm -f $(STAMPS)/$$s && echo "will re-run: $$s"; done

destroy: ## Delete the entire Kind cluster, recorded steps, and local data.
	@kind delete cluster --name $(KIND_NAME)
	@rm -rf $(ROOT)/.state
	@echo "removed recorded steps and .state keys; logs under $(LOGS) are kept"
