import { session } from '@web/session';
import { browser } from '@web/core/browser/browser';

function getColumnWidthKey(resModel, fieldName, viewId) {
	const parts = [
		session.db, resModel, fieldName, session.uid, viewId
	];
	const key = parts.reduce(
		(key, part) => key + ',' + part
	);
	return `muk_web_list_column.columnWidth:${key}`;
}

export function getColumnWidth(resModel, fieldName) {
	const key = getColumnWidthKey(resModel, fieldName);
	return browser.localStorage.getItem(key);
}

export function setColumnWidth(resModel, fieldName, data) {
	const key = getColumnWidthKey(resModel, fieldName);
	return browser.localStorage.setItem(key, data);
}

export function removeColumnWidth(resModel, fieldName, viewId) {
	const key = getColumnWidthKey(resModel, fieldName, viewId);
	return browser.localStorage.removeItem(key);
}
