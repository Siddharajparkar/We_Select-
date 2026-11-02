#!/usr/bin/env bash
# Ensure Microsoft ODBC Driver 18 for SQL Server is available on a GitHub-hosted Ubuntu runner.
set -euo pipefail

if odbcinst -q -d 2>/dev/null | grep -q "ODBC Driver 18 for SQL Server"; then
  echo "ODBC Driver 18 already installed"
  exit 0
fi

release="$(lsb_release -rs)"
curl -fsSL "https://packages.microsoft.com/config/ubuntu/${release}/packages-microsoft-prod.deb" -o /tmp/packages-microsoft-prod.deb
sudo dpkg -i /tmp/packages-microsoft-prod.deb
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev
odbcinst -q -d | grep "ODBC Driver 18 for SQL Server"
