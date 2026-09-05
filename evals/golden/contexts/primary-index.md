In Couchbase Capella, a primary index lets you run N1QL/SQL++ queries against a bucket or collection before any secondary indexes exist. It scans the entire keyspace, so it is meant for early development and ad-hoc queries, not production performance.

To create a primary index on a collection, run:

```sql
CREATE PRIMARY INDEX ON `bucket_name`.`scope_name`.`collection_name`;
```

For the default collection, the scope and collection qualifiers can be omitted:

```sql
CREATE PRIMARY INDEX ON `bucket_name`;
```

Once created, any SELECT query on that keyspace can execute even without a matching secondary index, falling back to a full primary scan.
