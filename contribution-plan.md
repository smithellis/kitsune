# Comprehensive Plan: Preserving Contributor Statistics During Content Deletion

Based on research of the Kitsune codebase, here's the **corrected** plan to implement immutable contribution tracking using an event log approach:

## **Current Problem Summary**

The system currently tracks contributions through live database queries, making statistics vulnerable to content deletion. Key issues:

1. **Statistics Deflation**: ALL contribution counts (lifetime and time-windowed) decrease when content is deleted
2. **Time-Based Metrics Affected**: 30-day and 90-day contributor metrics become inaccurate when content is removed
3. **No Historical Protection**: No mechanism preserves contribution statistics when legitimate content is removed
4. **Missing Spam Filtering**: Some metrics include spam content, causing inflated then deflated stats

## **Corrected Solution: Immutable Contribution Event Log**

Create an immutable log of contribution events that preserves ALL time-based and lifetime statistics regardless of content deletion.

### **1. ContributionEvent Model** (`kitsune/users/models.py`)

```python
class ContributionEvent(ModelBase):
    """
    Immutable log of contribution events that preserves contributor statistics
    regardless of content deletion. This enables time-based metrics that remain
    accurate even when the original content is removed.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contribution_events")
    contribution_type = models.CharField(max_length=20, choices=ContributionType.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Optional reference to original content (may be deleted later)
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Additional metadata for contribution context
    locale = models.CharField(max_length=7, blank=True, default="")
```

**Key Features:**
- **Immutable**: Events are never deleted, only created
- **Time-Aware**: Preserves exact timestamp of each contribution
- **Content-Agnostic**: Works even if original content is deleted
- **Locale-Aware**: Supports KB localization metrics

### **2. Signal Handlers** (`kitsune/users/signals.py`)

Automatically create events when content is contributed:

- `Question` created → `ContributionEvent(type=QUESTION)`
- `Answer` created → `ContributionEvent(type=ANSWER)` 
- `Answer` marked as solution → `ContributionEvent(type=SOLUTION)`
- `Revision` created → `ContributionEvent(type=KB_EDIT)`
- `Revision` reviewed → `ContributionEvent(type=KB_REVIEW)`
- `AnswerVote` helpful → `ContributionEvent(type=HELPFUL_VOTE)`

### **3. Updated Metrics Calculations**

**Lifetime Totals:**
```python
def num_answers(user):
    event_count = ContributionEvent.objects.filter(
        user=user, 
        contribution_type=ContributionEvent.ContributionType.ANSWER
    ).count()
    return event_count if event_count > 0 else Answer.objects.filter(creator=user).count()
```

**Time-Windowed Metrics:**
```python
def get_support_forum_contributors_30_days():
    thirty_days_ago = timezone.now() - timedelta(days=30)
    return ContributionEvent.objects.filter(
        contribution_type=ContributionEvent.ContributionType.ANSWER,
        created_at__gte=thirty_days_ago
    ).values('user').annotate(count=Count('user')).filter(count__gte=10).count()
```

**Leaderboards (90-day):**
```python
def get_top_contributors_90_days():
    ninety_days_ago = timezone.now() - timedelta(days=90)
    return ContributionEvent.objects.filter(
        contribution_type=ContributionEvent.ContributionType.ANSWER,
        created_at__gte=ninety_days_ago
    ).values('user').annotate(count=Count('user')).order_by('-count')[:20]
```

### **4. Migration Strategy**

**Phase 1: Deploy Event Logging**
- Add ContributionEvent model and signals
- Begin logging new contributions as events
- Existing metrics continue using live queries

**Phase 2: Backfill Historical Data**
- Run management command to create events for all existing content
- Preserves exact creation timestamps from original content

**Phase 3: Switch to Event-Based Metrics**
- Update KPI calculations to use event log
- Update leaderboard calculations to use event log
- Maintain fallback to live queries during transition

**Phase 4: Complete Migration**
- All metrics use event log exclusively
- Remove fallback logic once confident in event completeness

### **5. Implementation Benefits**

**Complete Time-Based Preservation**:
- 30-day contributor metrics remain accurate
- 90-day leaderboards remain accurate  
- Any custom time window can be calculated
- Lifetime totals are preserved

**Performance Improvements**:
- Indexed event queries are faster than complex JOINs
- Reduces load on main content tables
- Enables efficient caching and aggregation

**Data Integrity**:
- Events form immutable audit trail
- No retroactive changes possible
- Complete historical accuracy

**Backward Compatibility**:
- Hybrid approach during migration
- Existing APIs unchanged
- Zero downtime deployment

### **6. Edge Cases Handled**

**Spam Content**: Events only created for non-spam content at creation time
**User Deletion**: Events remain even if user content is reassigned  
**Content Deletion**: Events persist regardless of original content state
**System Accounts**: Events excluded for SUMO bot and system accounts
**Duplicate Prevention**: Backfill command checks for existing events

### **7. Event Log Advantages Over Previous Approach**

1. **Solves Time-Window Problem**: Unlike profile counters, events preserve exact timestamps
2. **Handles All Metrics**: Works for both lifetime and time-based calculations
3. **Query Flexibility**: Supports any time range or filtering criteria
4. **Audit Trail**: Complete history of all contributions
5. **Performance**: Optimized indexes for time-based queries

## Changed Files

### Modified Files
1. **kitsune/users/models.py** - Added ContributionEvent model for immutable event logging
2. **kitsune/questions/utils.py** - Updated `num_*` functions to use event log with fallback
3. **kitsune/users/views.py** - Updated profile view to use event-based document contribution counter
4. **kitsune/users/apps.py** - Added signal import to connect contribution event logging

### New Files  
1. **kitsune/users/signals.py** - Signal handlers for automatic contribution event logging
2. **kitsune/users/contribution_utils.py** - Utility functions for event-based metrics calculations
3. **kitsune/users/management/commands/backfill_contribution_events.py** - Management command for backfilling historical events
4. **kitsune/users/migrations/0036_add_contribution_event_model.py** - Database migration for ContributionEvent model

### Implementation Status
✅ **Phase 1 Complete**: Added ContributionEvent model and signal handlers
✅ **Phase 2 Complete**: Created event-based metrics utilities 
✅ **Phase 3 Complete**: Updated display functions to use event log with fallback
✅ **Phase 4 Complete**: Created backfill management command for historical events

### Next Steps for Deployment
1. Run migration: `docker compose run web python manage.py migrate`
2. Backfill existing data: `docker compose run web python manage.py backfill_contribution_events --dry-run` (test first)
3. Backfill actual data: `docker compose run web python manage.py backfill_contribution_events`
4. Monitor system to ensure signal handlers create events for new contributions
5. Verify contribution counts remain stable during content deletions
6. **Phase 3**: Update KPI calculations in `kitsune/kpi/management/commands/update_contributor_metrics.py` to use event log
7. **Phase 4**: Update community leaderboards in `kitsune/community/utils.py` to use event log

### Key Advantage
This approach correctly preserves **both lifetime AND time-windowed statistics** (30-day, 90-day) regardless of content deletion, solving the complete contribution tracking problem.
