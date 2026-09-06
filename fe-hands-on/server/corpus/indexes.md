# Primary indexes

In Couchbase Capella, a primary index lets you run N1QL/SQL++ queries against a bucket or collection before
any secondary indexes exist. It scans the entire keyspace, so it is meant for early development and ad-hoc
queries, not production performance.

To create a primary index on a collection:

```sql
CREATE PRIMARY INDEX ON `bucket_name`.`scope_name`.`collection_name`;
```

For the default collection, the scope and collection qualifiers can be omitted:

```sql
CREATE PRIMARY INDEX ON `bucket_name`;
```

Once created, any SELECT query on that keyspace can execute even without a matching secondary index, falling
back to a full primary scan.

# Secondary indexes

A secondary index covers specific fields, so queries filtering on those fields do not need a full scan. This
is what you use in production instead of a primary index.

```sql
CREATE INDEX idx_airline_country ON `travel-sample`.inventory.airline(country);
```

A query filtering on `country` can then use this index:

```sql
SELECT name FROM `travel-sample`.inventory.airline WHERE country = "United States";
```

Indexes are built asynchronously by default. To wait for the build to finish before the statement returns,
you can create the index deferred and build it explicitly.

# Dropping an index

```sql
DROP PRIMARY INDEX ON `bucket_name`;
DROP INDEX idx_airline_country ON `travel-sample`.inventory.airline;
```

Dropping a primary index while queries still depend on a full scan will cause those queries to fail with a
"No index available" error.
