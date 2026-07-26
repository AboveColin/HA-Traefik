# Traefik for Home Assistant

Monitor a [Traefik](https://traefik.io/traefik/) reverse proxy from Home
Assistant: how many routers and services it is serving, whether any of them
failed to load, when the configuration last reloaded, and how long your
certificates have left.

Unaffiliated with Traefik Labs.

[![hassfest](https://github.com/AboveColin/HA-Traefik/actions/workflows/main.yml/badge.svg)](https://github.com/AboveColin/HA-Traefik/actions/workflows/main.yml)
[![HACS](https://github.com/AboveColin/HA-Traefik/actions/workflows/HACSAction.yml/badge.svg)](https://github.com/AboveColin/HA-Traefik/actions/workflows/HACSAction.yml)

## Install

### HACS

1. HACS → **⋮** → **Custom repositories**
2. Add `https://github.com/AboveColin/HA-Traefik`, category **Integration**
3. Install **Traefik**, then restart Home Assistant
4. **Settings → Devices & Services → Add Integration → Traefik**

### Manually

Copy `custom_components/traefik` into your `config/custom_components/` folder
and restart Home Assistant.

## Set up

The API has to be enabled. In a static configuration that is:

```yaml
api:
  dashboard: true
```

and an entry point for it to listen on. If you also want the connection,
reload and certificate sensors, enable Prometheus metrics:

```yaml
metrics:
  prometheus:
    entryPoint: metrics
    addEntryPointsLabels: true
```

Then add the integration and fill in:

| Field | Example | Notes |
|---|---|---|
| Address | `http://192.0.2.10:8080` | Where the API listens. Pasting `/dashboard/` or `/api` on the end is fine — it gets stripped. |
| Username / Password | | Only if you put basic authentication in front of the API |
| Prometheus metrics address | `http://192.0.2.10:8082` | Optional, and usually a *different* port from the API |
| Verify the SSL certificate | on | Turn off only for a self-signed certificate on your own network |

After setup, use the integration's **Configure** button to pick individual
routers you want their own device and entities for. Every router is counted by
the instance sensors regardless — this is for the handful you want to alert on.

### If setup fails with "Access denied"

Traefik's API has no authentication of its own. It is normally locked down with
an `ipAllowList` middleware, which answers `403` to everyone else — including
Home Assistant. Add the Home Assistant host to that allow list. If Home
Assistant runs in a Docker bridge network, the address Traefik sees is the
docker host, not the container.

## Entities

One device for the instance:

| Entity | Description |
|---|---|
| HTTP routers | Routers currently loaded |
| HTTP router errors | Routers Traefik refused to load |
| HTTP services | Services currently loaded |
| HTTP service errors | Services Traefik refused to load |
| HTTP middlewares | Middlewares loaded (disabled by default) |
| TCP routers | TCP routers (disabled by default) |
| UDP routers | UDP routers (disabled by default) |
| Certificates | Certificates Traefik is holding |
| Certificate expiry | When the soonest-expiring certificate stops being valid — needs metrics |
| Open connections | Connections currently open — needs metrics |
| Configuration reloads | Successful reloads since start (diagnostic) — needs metrics |
| Last configuration reload | Timestamp of the last successful reload (diagnostic) — needs metrics |
| Entry points | Number of entry points (diagnostic, disabled by default) |
| Version | Traefik version (diagnostic) |
| Started | When the process started (diagnostic) |
| Configuration problem | `Problem` — on when any section reports errors |
| Backend unhealthy | `Problem` — on when an actively probed backend server is down |

One device per tracked router:

| Entity | Description |
|---|---|
| Status | `enabled`, `disabled` or `warning`, with rule, service, provider, priority, entry points, middlewares and TLS as attributes |
| Problem | `Problem` — on when the router is not enabled |

### A note on "Backend unhealthy"

Traefik only reports a server as down if that service has a
`loadBalancer.healthCheck` configured. Without one it reports every server as
`UP` forever, including servers that are switched off. So this sensor is
**unknown**, not "off", when nothing is being probed — claiming everything is
fine would be a lie your automations would act on.

To make it meaningful, give the services you care about a health check:

```yaml
http:
  services:
    example:
      loadBalancer:
        healthCheck:
          path: /health
          interval: 30s
        servers:
          - url: "http://192.0.2.20:8000"
```

## Automation example

Warn a fortnight before a certificate expires:

```yaml
automation:
  - alias: "Certificate expiring"
    triggers:
      - trigger: template
        value_template: >-
          {{ (as_timestamp(states('sensor.traefik_certificate_expiry'))
              - as_timestamp(now())) < 14 * 86400 }}
    actions:
      - action: notify.mobile_app_phone
        data:
          message: >-
            A Traefik certificate expires
            {{ as_timestamp(states('sensor.traefik_certificate_expiry')) | timestamp_local }}
```

## Polling

Four requests a minute, plus one for metrics if configured — all against a
service on your own network. Entry points are fetched once at setup, since they
only change when Traefik restarts.

## Troubleshooting

**"Traefik answered, but not with an API response"** — something else replied
on that address. Most often the address points at the web entry point serving
your sites rather than the API entry point.

**Certificate, connection and reload sensors are unavailable** — no metrics
address is set, or Prometheus metrics are not enabled in Traefik.

**A tracked router went unavailable** — it dropped out of the configuration.
The instance entities keep working.

For a bug report, attach diagnostics from the integration's ⋮ menu. Router
rules, certificate names, entry point addresses and your address are stripped
out of that file — only counts survive.

## Credits

Uses the [`traefik`](https://github.com/AboveColin/traefik) client library.

## License

MIT
