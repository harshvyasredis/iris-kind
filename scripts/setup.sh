#!/usr/bin/env bash
# Install host tools needed by this Makefile on macOS and Ubuntu 20.04+.
set -euo pipefail

KIND_VERSION="${KIND_VERSION:-v0.29.0}"
YQ_VERSION="${YQ_VERSION:-v4.45.4}"

have() {
  command -v "$1" >/dev/null 2>&1
}

os="$(uname -s)"
arch="$(uname -m)"
case "${arch}" in
  x86_64|amd64) arch="amd64" ;;
  aarch64|arm64) arch="arm64" ;;
  *)
    echo "unsupported architecture: ${arch}" >&2
    exit 1
    ;;
esac

bin_dir="/usr/local/bin"
if [[ ! -w "${bin_dir}" ]]; then
  if have sudo && sudo -n true 2>/dev/null; then
    :
  elif [[ -d "${HOME}/.local/bin" ]] || mkdir -p "${HOME}/.local/bin"; then
    bin_dir="${HOME}/.local/bin"
    export PATH="${bin_dir}:${PATH}"
  fi
fi

install_file() {
  local src="$1"
  local name="$2"
  chmod +x "${src}"
  if [[ -w "${bin_dir}" ]]; then
    mv "${src}" "${bin_dir}/${name}"
  elif have sudo; then
    sudo mv "${src}" "${bin_dir}/${name}"
  else
    mkdir -p "${HOME}/.local/bin"
    mv "${src}" "${HOME}/.local/bin/${name}"
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
}

download() {
  local url="$1"
  local dest="$2"
  if have curl; then
    curl -fsSL "${url}" -o "${dest}"
  elif have wget; then
    wget -qO "${dest}" "${url}"
  else
    echo "need curl or wget to download ${url}" >&2
    exit 1
  fi
}

apt_install() {
  local -a pkgs=("$@")
  local -a missing=()
  local pkg
  for pkg in "${pkgs[@]}"; do
    if ! dpkg -s "${pkg}" >/dev/null 2>&1; then
      missing+=("${pkg}")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    return 0
  fi
  if [[ "$(id -u)" -eq 0 ]]; then
    apt-get update -y
    apt-get install -y --no-install-recommends "${missing[@]}"
  elif have sudo; then
    sudo apt-get update -y
    sudo apt-get install -y --no-install-recommends "${missing[@]}"
  else
    echo "install packages as root: ${missing[*]}" >&2
    exit 1
  fi
}

install_uv() {
  if have uv; then
    echo "uv already installed: $(command -v uv)"
    return 0
  fi
  echo "installing uv into ${bin_dir}"
  # Official installer defaults to $HOME/.local/bin (root's home under sudo),
  # which is not on PATH for `sudo make validate`. Put it next to helm/kind.
  local env_prefix=(
    "UV_INSTALL_DIR=${bin_dir}"
    "UV_UNMANAGED_INSTALL=${bin_dir}"
    "UV_NO_MODIFY_PATH=1"
  )
  if have curl; then
    curl -LsSf https://astral.sh/uv/install.sh | env "${env_prefix[@]}" sh
  else
    wget -qO- https://astral.sh/uv/install.sh | env "${env_prefix[@]}" sh
  fi
  export PATH="${bin_dir}:${PATH}"
}

install_helm() {
  if have helm; then
    echo "helm already installed: $(command -v helm)"
    return 0
  fi
  echo "installing helm"
  local installer
  installer="$(mktemp)"
  download "https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3" "${installer}"
  chmod +x "${installer}"
  HELM_INSTALL_DIR="${bin_dir}" USE_SUDO="$([[ -w ${bin_dir} ]] && echo false || echo true)" bash "${installer}"
  rm -f "${installer}"
}

install_kubectl() {
  if have kubectl; then
    echo "kubectl already installed: $(command -v kubectl)"
    return 0
  fi
  echo "installing kubectl"
  local version tmp
  version="$(curl -fsSL https://dl.k8s.io/release/stable.txt)"
  tmp="$(mktemp)"
  download "https://dl.k8s.io/release/${version}/bin/$(uname -s | tr '[:upper:]' '[:lower:]')/${arch}/kubectl" "${tmp}"
  install_file "${tmp}" kubectl
}

install_kind() {
  if have kind; then
    echo "kind already installed: $(command -v kind)"
    return 0
  fi
  echo "installing kind ${KIND_VERSION}"
  local os_name tmp
  os_name="$(uname -s | tr '[:upper:]' '[:lower:]')"
  tmp="$(mktemp)"
  download "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-${os_name}-${arch}" "${tmp}"
  install_file "${tmp}" kind
}

install_yq() {
  if have yq && yq --version 2>/dev/null | grep -qi mikefarah; then
    echo "yq already installed: $(command -v yq)"
    return 0
  fi
  if have yq; then
    echo "replacing non-mikefarah yq at $(command -v yq)" >&2
  fi
  echo "installing yq ${YQ_VERSION}"
  local os_name tmp
  os_name="$(uname -s | tr '[:upper:]' '[:lower:]')"
  tmp="$(mktemp)"
  download "https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_${os_name}_${arch}" "${tmp}"
  install_file "${tmp}" yq
}

setup_macos() {
  if ! have brew; then
    echo "Homebrew is required on macOS. Install it from https://brew.sh then re-run make setup." >&2
    exit 1
  fi
  brew update
  brew install curl git jq yq kind kubernetes-cli helm
  if ! have uv; then
    brew install uv || install_uv
  fi
}

setup_linux() {
  if ! have apt-get; then
    echo "this setup script supports apt-based Linux (Ubuntu 20.04+)." >&2
    exit 1
  fi
  apt_install ca-certificates curl git jq make
  install_uv
  install_helm
  install_kubectl
  install_kind
  install_yq
}

echo "installing host tools for ${os}/${arch}"
case "${os}" in
  Darwin) setup_macos ;;
  Linux) setup_linux ;;
  *)
    echo "unsupported OS: ${os}" >&2
    exit 1
    ;;
esac

export PATH="${HOME}/.local/bin:/usr/local/bin:${PATH}"

echo
echo "installed:"
for tool in curl git jq yq uv helm kubectl kind make; do
  if have "${tool}"; then
    printf '  %-8s %s\n' "${tool}" "$(command -v "${tool}")"
  else
    printf '  %-8s MISSING\n' "${tool}" >&2
    missing=1
  fi
done

if ! have docker; then
  echo
  echo "docker is not installed. Start Docker Desktop (macOS) or install Docker Engine (Ubuntu), then re-run make validate." >&2
fi

if [[ "${missing:-0}" -eq 1 ]]; then
  echo "one or more tools are still missing; add ${HOME}/.local/bin to PATH if uv/helm landed there." >&2
  exit 1
fi

echo
echo "next: drop license files next to README.md, then make validate && make all"
