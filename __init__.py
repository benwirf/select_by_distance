#-----------------------------------------------------------
# Copyright (C) 2022 Ben Wirf
#-----------------------------------------------------------
# Licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#---------------------------------------------------------------------

import os

from PyQt5.QtCore import Qt

from PyQt5.QtGui import QIcon, QCursor, QColor

from PyQt5.QtWidgets import QAction, QInputDialog, QToolBar

from qgis.core import (QgsProject, QgsDistanceArea, QgsWkbTypes,
    QgsGeometry, QgsMapLayer, QgsSpatialIndex, QgsCoordinateTransform,
    QgsUnitTypes, QgsPointXY, QgsMapLayerType)

from qgis.gui import QgsRubberBand, QgsMapToolEmitPoint

def classFactory(iface):
    return SelectByDistance(iface)


class SelectByDistance:
    def __init__(self, iface):
        self.iface = iface
        self.map_tool = None

    def initGui(self):
        self.folder_name = os.path.dirname(os.path.abspath(__file__))
        self.icon_path = os.path.join(self.folder_name, 'select_icon.png')
        self.action = QAction(QIcon(self.icon_path), 'Select By Distance', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.toolbar = self.iface.mainWindow().findChild(QToolBar, 'mSelectionToolBar')
        self.toolbar.addAction(self.action)
        self.project = QgsProject.instance()
        self.project.layersAdded.connect(self.layers_added)
        self.project.layersRemoved.connect(self.layers_removed)
        self.iface.projectRead.connect(self.project_read)
        self.iface.newProjectCreated.connect(self.project_created)
        self.manage_action()
                
    def unload(self):
        self.project.layersAdded.disconnect(self.layers_added)
        self.project.layersRemoved.disconnect(self.layers_removed)
        self.iface.projectRead.disconnect(self.project_read)
        self.iface.newProjectCreated.connect(self.project_created)
        self.toolbar.removeAction(self.action)
        del self.action
        
    def project_read(self):
        self.project.layersAdded.disconnect(self.layers_added)
        self.project.layersRemoved.disconnect(self.layers_removed)
        self.project = QgsProject.instance()
        self.manage_action()
        self.project.layersAdded.connect(self.layers_added)
        self.project.layersRemoved.connect(self.layers_removed)
        
    def project_created(self):
        self.project.layersAdded.disconnect(self.layers_added)
        self.project.layersRemoved.disconnect(self.layers_removed)
        self.project = QgsProject.instance()
        self.manage_action()
        self.project.layersAdded.connect(self.layers_added)
        self.project.layersRemoved.connect(self.layers_removed)
        
    def layers_added(self):
        self.manage_action()
        
    def layers_removed(self):
        self.manage_action()

    def manage_action(self):
        if self.project:
            vector_lyrs = [l for l in self.project.mapLayers().values() if l.type() == QgsMapLayerType.VectorLayer]
            if not vector_lyrs:
                self.iface.actionPan().trigger()
                if self.action.isEnabled():
                    self.action.setEnabled(False)
            else:
                if not self.action.isEnabled():
                    self.action.setEnabled(True)

    def run(self):
        units = QgsProject.instance().crs().mapUnits()
        unitstr = QgsUnitTypes.encodeUnit(units)
        dist, ok = QInputDialog().getDouble(self.iface.mainWindow(), 'Select by distance', f'Enter search distance (<b>{unitstr}</b>)', min=0.0, decimals=3)
        if ok:
            self.map_tool = MapToolSelectByDistance(self.iface, dist)
            self.iface.mapCanvas().setMapTool(self.map_tool)
        
        
class MapToolSelectByDistance(QgsMapToolEmitPoint):
    
    def __init__(self, iface, radius):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        QgsMapToolEmitPoint.__init__(self, self.canvas)
        self.cursor = QCursor()
        self.cursor.setShape(Qt.ArrowCursor)
        self.setCursor(self.cursor)
        self.radius = radius
        self.pnt = None
        self.rb = None
        self.da = QgsDistanceArea()
        self.da.setSourceCrs(QgsProject.instance().crs(), QgsProject.instance().transformContext())
        QgsProject.instance().crsChanged.connect(self.project_crs_changed)
        self.canvas.extentsChanged.connect(self.draw_rb_at_mouse_pos)
#        self.draw_rb_at_mouse_pos()
    
    def draw_rb_at_mouse_pos(self):
        self.pnt = self.toMapCoordinates(self.canvas.mouseLastXY())
#        print(self.pnt)
        self.draw_rubber_band(self.pnt, self.radius)
            
    def draw_rubber_band(self, centre, radius):
        if self.rb:
            self.rb.reset()
        self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rb.setStrokeColor(QColor('red'))
        self.rb.setWidth(0.1)
        pnt_geom = QgsGeometry().fromPointXY(centre)
        search_area = pnt_geom.buffer(radius, 24)
        self.rb.setToGeometry(search_area)
            
    def canvasMoveEvent(self, e):
        self.pnt = e.mapPoint()
        self.draw_rubber_band(self.pnt, self.radius)
    
    def canvasPressEvent(self, e):
#        print(e.mapPoint())
        lyr = self.iface.activeLayer()
        if e.button() == Qt.LeftButton:
            if not lyr:
                self.iface.messageBar().pushMessage('No layers in Project!')
                return
            if lyr.type() == QgsMapLayer.VectorLayer:
                idx = QgsSpatialIndex(lyr.getFeatures())
                pnt_geom = QgsGeometry().fromPointXY(e.mapPoint())
                search_area = pnt_geom.buffer(self.radius, 24)
                xform = QgsCoordinateTransform(QgsProject.instance().crs(), lyr.crs(), QgsProject.instance())
                search_area_xform = search_area.transform(xform)
                lyr.selectByIds([f.id() for f in lyr.getFeatures(idx.intersects(search_area.boundingBox())) if f.geometry().intersects(search_area)])
        elif e.button() == Qt.RightButton:
            self.rb.reset()
            units = QgsProject.instance().crs().mapUnits()
            unitstr = QgsUnitTypes.encodeUnit(units)
            dist, ok = QInputDialog().getDouble(self.iface.mainWindow(), 'Select by distance', f'Enter search distance ({unitstr})', value= self.radius, min=0.0, decimals=3)
            if ok:
                self.radius = dist
            
    def project_crs_changed(self):
        r = self.da.convertLengthMeasurement(self.radius, QgsProject.instance().crs().mapUnits())
        self.radius = r
        self.da.setSourceCrs(QgsProject.instance().crs(), QgsProject.instance().transformContext())
    
    def deactivate(self):
        self.canvas.extentsChanged.disconnect(self.draw_rb_at_mouse_pos)
        QgsProject.instance().crsChanged.disconnect(self.project_crs_changed)
        if self.rb:
            self.rb.reset()
