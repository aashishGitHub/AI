# Buckets, scopes and collections

Couchbase organises data in three levels:

- **Bucket** — the top-level container, roughly analogous to a database. Memory and disk quotas are set here.
- **Scope** — a namespace inside a bucket, roughly analogous to a schema. Useful for multi-tenancy or for
  separating one application's data from another's.
- **Collection** — holds the actual JSON documents, roughly analogous to a table.

A fully qualified keyspace is therefore `bucket.scope.collection`, for example
`` `travel-sample`.inventory.airline ``.

Every bucket has a `_default` scope containing a `_default` collection. Documents written without specifying
a scope or collection land there, which is why simple examples can address a bucket by name alone.

# Documents and keys

Each document has a unique key within its collection and a JSON body. Keys are strings, and choosing them
well matters: a key-value read by key is the fastest operation Couchbase offers, far faster than a query.

```sql
SELECT META().id, name FROM `travel-sample`.inventory.airline LIMIT 5;
```

`META().id` exposes the document key inside a query.

# Basic SELECT syntax

SQL++ (formerly N1QL) queries JSON with SQL-like syntax:

```sql
SELECT name, country
FROM `travel-sample`.inventory.airline
WHERE country = "France"
ORDER BY name
LIMIT 10;
```

Nested fields are addressed with dot notation, and arrays with subscripts:

```sql
SELECT geo.lat, geo.lon FROM `travel-sample`.inventory.airport WHERE airportname = "Heathrow";
```
