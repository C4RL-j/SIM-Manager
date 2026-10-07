docs/carriers/DITO.md

# DITO Adapter

Status: Active development

## Authentication

Official source:
MyDITO website.

Desired flow:

SIM Manager
→ Login to DITO
→ official login page
→ user authenticates
→ session becomes available
→ DITO adapter reads account data

## Never store

- OTP
- plaintext password
- raw account credentials

## Account data

Normalized fields:

data_remaining
load_balance
promo_name
promo_expiry
calls_remaining
texts_remaining

## Unknowns

- exact authentication implementation
- session lifetime
- API/network endpoints
- CAPTCHA behavior

These must be investigated rather than guessed.