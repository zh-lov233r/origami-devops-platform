#!/bin/sh
# 中文：渲染 SSO Nginx 配置，将内部 API token 注入只读容器中的运行时配置。
# English: Render the SSO Nginx config, injecting the internal API token into runtime config.

set -eu

: "${ORIGAMI_API_TOKEN:?Set ORIGAMI_API_TOKEN for the trusted proxy}"

sed "s|__ORIGAMI_API_TOKEN__|${ORIGAMI_API_TOKEN}|g" \
  /etc/nginx/templates/origami-sso.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g "daemon off;"
