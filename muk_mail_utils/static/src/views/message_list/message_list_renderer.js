import { ListRenderer } from '@web/views/list/list_renderer';

export class MessageListRenderer extends ListRenderer {
    static props = [...ListRenderer.props, 'setSelectedRecord?'];
    onCellClicked(record, column, ev) {
        this.props.setSelectedRecord(record);
        super.onCellClicked(record, column, ev);
    }
    findFocusFutureCell(cell, cellIsInGroupRow, direction) {
        const futureCell = super.findFocusFutureCell(
            cell, cellIsInGroupRow, direction
        );
        if (futureCell) {
            const dataPointId = futureCell.closest('tr').dataset.id;
            const records = this.props.list.records.filter(
                (x) => x.id === dataPointId
            );
            this.props.setSelectedRecord(records[0]);
        }
        return futureCell;
    }
}
