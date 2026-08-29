# Traefik for Home Assistant

Monitor a [Traefik](https://traefik.io/traefik/) reverse proxy from Home
Assistant. Every route becomes its own device, named after the hostname it
serves, with its own traffic, error rate, response time, backend health and
certificate expiry, so "something is broken" becomes "`git.example.com` is
throwing 500s".

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
    addServicesLabels: true
```

Both label options default to on. `addServicesLabels` is what makes per-route
traffic possible: Traefik does not export per-router counters, so requests,
errors and response times are read from the service each router forwards to.

Then add the integration and fill in:

| Field | Example | Notes |
|---|---|---|
| Address | `http://192.0.2.10:8080` | Where the API listens. Pasting `/dashboard/` or `/api` on the end is fine, it gets stripped. |
| Username / Password | | Only if you put basic authentication in front of the API |
| Prometheus metrics address | `http://192.0.2.10:8082` | Optional, and usually a *different* port from the API |
| Verify the SSL certificate | on | Turn off only for a self-signed certificate on your own network |

Every route is tracked by default, and routes added to Traefik later appear on
the next poll without a reload. On a large instance that is a lot of entities;
the integration's **Configure** button can turn tracking off and let you pick
the handful of routes you actually want to alert on instead.

### If setup fails with "Access denied"

Traefik's API has no authentication of its own. It is normally locked down with
an `ipAllowList` middleware, which answers `403` to everyone else, including
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
| Certificates | Certificates Traefik is holding, with common name, SANs and expiry per certificate as attributes |
| Hostnames | Distinct hostnames served, listed as an attribute |
| Requests | Requests handled since start. Needs metrics. |
| Request errors | 4xx and 5xx responses since start. Needs metrics. |
| Error rate | Share of responses that were 4xx or 5xx. Needs metrics. |
| Average response time | Mean response time since start. Needs metrics. |
| Certificate expiry | When the soonest-expiring certificate stops being valid. Needs metrics. |
| Open connections | Connections currently open, broken down per entry point as an attribute. Needs metrics. |
| Configuration reloads | Successful reloads since start (diagnostic). Needs metrics. |
| Last configuration reload | Timestamp of the last successful reload (diagnostic). Needs metrics. |
| Entry points | Number of entry points (diagnostic, disabled by default) |
| Version | Traefik version (diagnostic) |
| Started | When the process started (diagnostic) |
| Configuration problem | `Problem`, on when any section reports errors |
| Backend unhealthy | `Problem`, on when an actively probed backend server is down |

One device per tracked route, named after its hostname:

| Entity | Description |
|---|---|
| Status | `enabled`, `disabled` or `warning`, with hostnames, rule, service, provider, priority, entry points, middlewares, TLS, backend servers and the covering certificate as attributes |
| Requests | Requests this route's service handled. Needs metrics. |
| Request errors | 4xx and 5xx responses (disabled by default). Needs metrics. |
| Error rate | Share of responses that were 4xx or 5xx (disabled by default). Needs metrics. |
| Average response time | Mean response time (disabled by default). Needs metrics. |
| Certificate expiry | Expiry of the certificate covering this hostname (disabled by default). Needs metrics. |
| Problem | `Problem`, on when the router is not enabled |
| Backend unhealthy | `Problem`, on when this route's backend is down (see below) |

A route matching on a path or header rather than a host keeps its configured
router name, since there is no hostname to use. Certificates are matched
tightest-first, so a host with its own certificate does not report the expiry
of the wildcard that also happens to cover it.

### A note on "Backend unhealthy"

Traefik only reports a server as down if that service has a
`loadBalancer.healthCheck` configured. Without one it reports every server as
`UP` forever, including servers that are switched off. So this sensor is
**unknown**, not "off", when nothing is being probed. Claiming everything is
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

Or catch a route that starts failing:

```yaml
automation:
  - alias: "Route erroring"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.git_example_com_error_rate
        above: 5
        for: "00:05:00"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "git.example.com is at {{ states('sensor.git_example_com_error_rate') }}% errors"
```

Error rate and average response time are lifetime figures, not a moving
window: they are computed from Traefik's own totals, which is all Prometheus
exposes without a time-series database behind it. They move slowly on a
long-running instance.

## Polling

Four requests a minute, plus one for metrics if configured, all against a
service on your own network. Entry points are fetched once at setup, since they
only change when Traefik restarts.

## Troubleshooting

**"Traefik answered, but not with an API response"**. Something else replied
on that address. Most often the address points at the web entry point serving
your sites rather than the API entry point.

**Certificate, connection and reload sensors are unknown**. No metrics
address is set, or Prometheus metrics are not enabled in Traefik. These
entities stay available and report unknown, they do not go unavailable.

**A tracked router went unavailable**. It dropped out of the configuration.
The instance entities keep working.

For a bug report, attach diagnostics from the integration's ⋮ menu. Router
rules, hostnames, certificate names, backend server URLs, entry point
addresses and your address are stripped out of that file, so only counts
survive.

## Credits

Uses the [`traefik`](https://github.com/AboveColin/traefik) client library.

## License

MIT
