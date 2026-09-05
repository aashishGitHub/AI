# Vector Databases — In Plain Sentences

> The whole topic retold as prose, no tables. For revision on a walk, or the night before, when you want the
> argument rather than the lookup. Each section hands off to the next.

---

**Start with what a vector actually is.** An embedding model reads a piece of text and returns a long list of
numbers — say 1536 of them — positioned so that things which mean similar things end up near each other.
"Near" is geometry: cosine angle, or straight-line distance. The important consequence is that this
positioning only holds *inside one model's space*. Two vectors from two different models are not near or far;
they are simply not comparable, even if both have 1536 numbers. So the write path and the read path must use
the same model, the same dimensions, and the same distance metric. Nothing in the system will check this for
you, and a mismatch does not raise an error — it just quietly ruins your results. That silence is a theme, and
it starts here.

**Which brings us to the compromise at the heart of everything.** To find the nearest vectors exactly, you
must compare the query against every single one. For ten million vectors of 1536 dimensions that is about
fifteen billion arithmetic operations per query, and it grows in a straight line as your corpus grows. Nobody
can afford that on a request path, so every vector database replaces exact search with *approximate* search.
Read that word carefully, because you have just agreed to be wrong sometimes. Not slow — wrong. And the
system will not tell you when it happens.

**That silence is the single most important operational fact in the subject.** A badly tuned index returns
exactly the ten results you asked for, in confident rank order, with perfectly normal latency. It looks
identical to a perfectly tuned one. This is why the metric that matters is recall — of the truly nearest ten
neighbours, how many did you actually get back? — and also why almost nobody measures it. Latency has a graph
on a dashboard and wakes someone at two in the morning. Recall has neither, unless you deliberately build it.
The way you build it is cheaper than people expect: take about a thousand representative queries, run exact
brute-force search over them offline where no user is waiting, store those true answers as a fixture, and
compare your index against it every night.

**Now, how the approximation actually works.** There are two main families. HNSW builds a graph in layers: the
top layers are sparse with long jumps across the space, the bottom layer contains every item with only short
links to close neighbours. A search enters at the top, greedily walks toward the query, drops down a layer
when no neighbour is closer, and finishes with a careful local look around at the bottom. It is a skip list,
applied to proximity. IVF does something different: it clusters everything with k-means, and at query time
compares only against the cluster centroids, then searches inside the nearest few clusters. It is cheaper to
build and needs less memory, but it has a distinctive flaw — a genuinely close neighbour sitting just over a
cluster boundary is never even considered. IVF also has to see representative data before it can be built at
all, because it needs to train those centroids. HNSW does not, which is a large part of why HNSW is the
sensible default.

**HNSW's knobs are worth knowing precisely, because they are not equal.** Two of them, the number of links per
node and the effort spent during construction, are baked in at build time; changing them means rebuilding the
whole index. The third, the size of the candidate list at query time, is free to change per query. That
asymmetry is the useful part. It means recall is a live dial you can turn without a rebuild, and it means you
can be generous for a background job and stingy for an interactive one. Most teams set one global value and
never touch it again, which is a missed opportunity — and it also sets up the trap where an index tuned when
the corpus held one million items is quietly under-tuned by the time it holds fifty million, because recall
falls as the corpus grows even when the settings do not change.

**Then there is memory, which is mostly just multiplication.** Ten million vectors, 1536 dimensions, four
bytes per number, comes to about sixty-one gigabytes. The graph structure on top is under a gigabyte — a
rounding error by comparison. So the vectors themselves decide which machine you need, and the way to change
that answer is quantization: store each number in one byte instead of four and you divide by four; store each
dimension as a single bit and you divide by thirty-two. The catch is that you have thrown away precision, so
the ordering you get back is approximate in a second way. The repair is to fetch more candidates than you need
using the compressed vectors, then re-score just those candidates against the full-precision originals. Which
means you still have to keep the originals somewhere. Quantization makes the scan cheap; it does not make the
storage disappear.

**And now the part that separates people who have read about this from people who have run it: filtering.**
Real queries are almost never "find similar things". They are "find similar things belonging to this
customer". You would think this is easy — it is a `WHERE` clause — but it collides with how graph search
works. If you search first and filter afterwards, you asked for ten results, nine belonged to other customers,
and you hand back one; how many survive depends on where that customer's data happens to sit, so the shortfall
is unpredictable. If instead you filter first and then search, you have deleted nodes from the graph, and the
graph reached good answers precisely by hopping through its neighbours. Remove the stepping stones and the
path to the right answer is severed. You get results, they look fine, they are wrong. Both strategies fail;
they just fail differently.

**The way out is to ask how selective the filter is, and the answer inverts at both ends.** If the filter
matches almost everything, search first and filter after — barely anything gets discarded. If the filter is
brutally selective — say a tenth of a percent of ten million items, which is ten thousand vectors — then the
correct move is to stop using the clever index altogether and compare against all ten thousand directly. That
is exact, it is fast, and it gives perfect recall. Knowing when to abandon the sophisticated structure is a
stronger signal in an interview than being able to explain how it works. The genuinely difficult territory is
the middle, and that is precisely where engines differentiate themselves. It is also why multi-tenancy is
usually better solved by giving each large tenant its own index: that converts a hard filtering problem into
an easy routing problem.

**With that settled, you can talk about where the vectors should live — and this is a different question than
it first appears.** Arguments about which vector database is best are usually conducted as performance
arguments, when they are really arguments about data topology. If your vectors sit in the same database as
your source of truth, a write is one transaction and either it happened or it did not. If your vectors live in
a separate service, every write has to land in two places, and eventually one of them will fail while the
other succeeds. When that happens you get a row with no vector: a document that exists, that your search can
never find, forever, with no error logged anywhere and nothing to alert on. Fixing that properly means an
outbox, or change-data-capture, or a reconciliation job — real engineering that must be staffed. That is the
tax on separation, and it should be named out loud before anyone chooses a vendor.

**Vendors are also less monolithic than they used to be.** Couchbase 8.0, for instance, does not ship one
vector index but three, and the differences are exactly the trade-offs above made explicit. One is built for
pure similarity search, keeps most of itself on disk so it needs little memory, and scales to billions — but
does no filtering at all. A second supports filtering by scalar values before the vector search runs, which is
useful when those filters eliminate most of the data, and the documentation openly says that filtering first
can miss relevant results. A third combines vector search with full-text and geospatial search in a single
pass, at a smaller scale ceiling. The lesson generalises past any one vendor: the index follows the shape of
the query, so one application with three kinds of query may quite reasonably keep three indexes over the same
data.

**Whatever you choose, pure vector search alone will not be enough.** Embeddings capture meaning, which means
they are weakest exactly where strings are most precise. An error code, a product SKU, a version number — these
carry almost no learned meaning, so the model smears them into a vague neighbourhood of similar-looking
tokens. Old-fashioned keyword search handles them perfectly and fails at synonyms, which is the mirror image.
So you run both and merge the results, and the standard way to merge is to combine by rank rather than by
score, because a relevance score from keyword search and a cosine similarity are not measured in the same
units and never will be. Then, because the index was only ever chosen for speed, you take the merged
candidates and re-rank them with a slower, more accurate model that reads the query and each document
together. Fetch wide and cheap for recall; narrow down accurately for precision. And remember the ceiling: a
re-ranker can only reorder what it was handed, so if the right document was never retrieved, no amount of
re-ranking will conjure it.

**Finally, think in years, because the thing you build will change underneath you.** Your embedding model will
eventually be deprecated, and since a new model means a new geometry, there is no upgrade in place — old and
new vectors cannot be compared at all. What you do instead is build a second index alongside the first, write
every new document to both, re-embed the entire corpus in the background, run live queries against the new one
without serving its results until you have compared quality, then move traffic over gradually and keep the old
one warm until you are sure. That means paying to embed everything again and storing two full indexes at once,
which is why it is a project and not a task, and why recording which model produced each vector is a small
discipline that saves you enormously later.

**Meanwhile the index decays quietly on its own.** Deleting from a graph is awkward, because the node you want
gone may be the stepping stone others rely on, so engines mark it as deleted while leaving it in place to be
walked through. Those markers accumulate, and recall drifts downward over months. Add corpus growth, which
lowers recall at unchanged settings, and you have a complete explanation for the most confusing incident in
this field: quality fell, and nobody deployed anything. Nothing was deployed, but the data changed, and the
data is part of the system.

**Which loops back to where we started.** Every real decision here — graph or clusters, compressed or full
precision, filter before or after, one index or one per tenant, in your database or in someone else's — is the
same decision wearing different clothes: how much recall are you selling, and is anyone reading the bill? The
engineers who do this well are not the ones who memorised the index structures. They are the ones who can tell
you their recall number, say how they measured it, and name the day it will start to drop.
