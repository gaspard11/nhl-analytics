"""Tables that sort when a column header is clicked, with the sorted column highlighted.

Drawn with AG Grid (streamlit-aggrid) rather than st.dataframe: st.dataframe sorts in the browser
without telling Python, so a highlight or a rank can't follow a click. Here the sort, the highlight
and the rank all happen in the browser, in the JavaScript below (ours, hence allow_unsafe_jscode).
Used by the Standings and Player stats pages.
"""

from st_aggrid import AgGrid, JsCode
from st_aggrid.shared import StAggridTheme


HEADER_HEIGHT = 36  # pixels, as in st.dataframe
HIGHLIGHT_STYLE = {"background-color": "#e8eefc !important", "color": "#1f3b8f !important"}  # the sorted column

# Same look as st.dataframe: grey header with grey text, white rows without stripes, thin light
# borders, rounded corners, Source Sans (loaded by the grid, which runs in its own frame)
THEME = StAggridTheme(base="quartz").withParams(
    fontFamily={"googleFont": "Source Sans 3"},
    fontSize=14,
    headerFontSize=14,
    headerFontWeight=400,
    foregroundColor="rgb(49, 51, 63)",
    backgroundColor="#ffffff",
    oddRowBackgroundColor="#ffffff",
    headerBackgroundColor="rgb(248, 249, 251)",
    headerTextColor="rgb(129, 131, 139)",
    borderColor="rgb(234, 234, 235)",
    rowBorder=True,
    columnBorder=True,
    headerColumnBorder=True,
    headerColumnResizeHandleColor="transparent",  # st.dataframe only has the full column lines
    wrapperBorder=True,
    wrapperBorderRadius=8,
    rowHoverColor="rgba(49, 51, 63, 0.04)",
    cellHorizontalPadding=8,
    headerHeight=HEADER_HEIGHT,
)

CUSTOM_CSS = {
    ".sorted-column": HIGHLIGHT_STYLE,
    # The header is highlighted through the aria-sort attribute AG Grid sets on the sorted column
    '.ag-header-cell[aria-sort="ascending"], .ag-header-cell[aria-sort="descending"]': HIGHLIGHT_STYLE,
    ".ag-cell": {"display": "flex", "align-items": "center"},  # images and numbers vertically centred
    ".ag-right-aligned-cell": {"justify-content": "flex-end"},  # numbers on the right, as in st.dataframe
}

# Image cell (headshot, logo, icons), as tall as the column's cellRendererParams imageHeight.
# A class with getGui: the React version of AG Grid doesn't accept a function returning an element
IMAGE_RENDERER = JsCode("""
class ImageRenderer {
    init(params) {
        this.img = document.createElement('img');
        this.img.src = params.value || '';
        this.img.style.display = params.value ? '' : 'none';
        this.img.style.height = params.imageHeight + 'px';
        this.img.style.maxWidth = '100%';
        this.img.style.objectFit = 'contain';
    }
    getGui() { return this.img; }
    refresh() { return false; }
}
""")

# A cell is highlighted when its column is the one the table is sorted by
IS_SORTED_COLUMN = JsCode("function(params) { return !!params.column.getSort(); }")

# After a sort, redraw the cells so the highlight follows the sorted column
REFRESH_CELLS = JsCode("function(params) { params.api.refreshCells({force: true}); }")

# Same, after numbering the rows in their new order in the RANK field, equal values sharing a
# rank (1, 2, 2, 4)
RECOMPUTE_RANKS = JsCode("""
function(params) {
    const sorted = params.api.getColumnState().find(column => column.sort);
    let position = 0, rank = 0, previous;
    params.api.forEachNodeAfterFilterAndSort(node => {
        position += 1;
        const value = sorted ? node.data[sorted.colId] : position;
        if (position === 1 || value !== previous) rank = position;
        previous = value;
        node.data.RANK = rank;
    });
    params.api.refreshCells({force: true});
}
""")

# Column types, to unpack in a column definition. Numbers sort highest first on the first click,
# text alphabetically. Small minimum widths, so the columns fit without scrolling on a laptop
NUMBER_COLUMN = {"type": "numericColumn", "sortingOrder": ["desc", "asc"], "flex": 1, "minWidth": 70}
TEXT_COLUMN = {"sortingOrder": ["asc", "desc"], "flex": 2, "minWidth": 120}
UNSORTABLE = {"sortable": False}


def image_column(width, image_height):
    """Column definition parts for an image cell, centred."""
    return {
        "cellRenderer": IMAGE_RENDERER,
        "cellRendererParams": {"imageHeight": image_height},
        "cellStyle": {"justifyContent": "center"},
        "sortable": False,
        "width": width,
    }


def sortable_table(data, column_defs, row_height, key, rank_column=False, max_height=2000):
    """AG Grid table of data's columns listed in column_defs, sorted at first by the column whose
    definition has a "sort". With rank_column, the RANK field is recomputed after every sort.
    key: a new key for every new data, so the table is never stale."""
    columns = [column["field"] for column in column_defs]
    on_sort = RECOMPUTE_RANKS if rank_column else REFRESH_CELLS
    grid_options = {
        "columnDefs": column_defs,
        "defaultColDef": {"cellClassRules": {"sorted-column": IS_SORTED_COLUMN}},
        "rowHeight": row_height,
        "headerHeight": HEADER_HEIGHT,
        "onSortChanged": on_sort,
        "onFirstDataRendered": on_sort,
        "suppressCellFocus": True,
        # Header tooltips (headerTooltip) show after 0.3 s instead of AG Grid's default 2 s
        "tooltipShowDelay": 300,
        "loadThemeGoogleFonts": True,
    }
    AgGrid(
        data.assign(RANK=None)[columns] if rank_column else data[columns],
        gridOptions=grid_options,
        # Header + every row, so a short table shows in full; a long one scrolls inside itself
        height=min(HEADER_HEIGHT + len(data) * row_height + 3, max_height),
        theme=THEME,
        custom_css=CUSTOM_CSS,
        allow_unsafe_jscode=True,
        # Sorting stays in the browser: no rerun of the page, nothing sent back to Python
        update_on=[],
        show_toolbar=False,
        key=key,
    )
