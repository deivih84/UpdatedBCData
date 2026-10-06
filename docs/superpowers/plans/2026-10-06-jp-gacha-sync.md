# JP gacha automation implementation plan

Goal: extend the existing EN maintenance flow to JP while preserving EN defaults.
Approved design: shared --region jp command; separate catalog/cache/state/reports,
JP pools and complete JP artwork, periodic workflow and compatible app calendar.

1. Add explicit region selection to sources, local pack loading and pure planners.
   Verify JP language, Unicode names, variant labels and image filename isolation.
2. Add JP CLI paths and calendar lookup that accepts verified catalog identities
   rather than Japanese advertising headlines. Keep N/E and R ID namespaces separate.
3. Initialize JP data from verified JP pack/wiki associations, run dry-run/apply,
   validate online providers and repeat to verify unchanged content.
4. Extend workflow/docs, copy artwork to both destinations, run full tests and
   both animation dry-runs; review before reporting completion.

Constraints: no EN pool/cache/image copying into JP; no credential commits;
unknown identities/images remain pending; retain scheduled pool variants.
