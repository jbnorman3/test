# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# photo_parsing.py
# Created on: 2018-08-06 08:13:51.00000
# Description: this tool reads in a pre-processed table that then is used to group phots into < 1000 photo blocks based on waterhed boundaries
# ---------------------------------------------------------------------------

# Import arcpy module
# Import system modules
import arcgisscripting,sys, string, os, re, time #, win32com.client, win32api
from time import *

# Create the Geo processor object
#gp = win32com.client.Dispatch("esriGeoprocessing.GpDispatch.1")
gp = arcgisscripting.create()
import arcpy
from arcpy import env
from arcpy.sa import *

#USER input data
HUCfeatures = sys.argv[1]
photofeatures = sys.argv[2]

OutCVS = sys.argv[3]
TempSpace = sys.argv[4]


#################################################################################
#  Create a temp workspace to hold temp data          ###########################
#################################################################################
gp.Workspace = TempSpace
strWS = "photo" + strftime("%Y%m%d%H%M%S", localtime())
gp.CreateFolder ( gp.Workspace, strWS )
gp.Workspace = gp.Workspace + "\\" + strWS
gp.AddMessage(" ")
gp.AddMessage("Writing Elevation mask temporary files to workspace: " + gp.Workspace )

gp.overwriteoutput = 1

#################################################################################
#################################################################################


#################################################################################
#      Set up variables     ####################################################
#################################################################################
photoPTS = gp.Describe(photofeatures).Path + "\\" + gp.Describe(photofeatures).Name
HUCfeat = gp.Describe(HUCfeatures).Path + "\\" + gp.Describe(HUCfeatures).Name

#open file to write to
#gp.AddMessage(OutCVS)
TempXYFile = gp.Workspace + "\\group1.txt"
ofh = open(TempXYFile, "w")
#wirte CSV file header
print >>ofh, "group,xval,yval"

#local variables
interHUC_pts = gp.Workspace + "\\photohucs" #points intersected with HUC boundaries
photoHUCs = gp.Workspace + "\\hucs.shp" # HUCs that have photos in them
buffHUC = gp.Workspace + "\\buffhuc" #buffered HUCs
summaryHUC = gp.Workspace + "\\huc_count.dbf" #tabel that holds the number of photos in each HUC
HUCraster = gp.Workspace + "\\hucras" #rasterized version of photoHUCs
HUCVariety = gp.Workspace + "\\varietyhuc" #moving window with boundaries
varetygt = gp.Workspace + "\\vargt2" #intersections greater than two
VARAllo = gp.Workspace + "\\varallo" #this is the ex extended raster form the varetygt raster  
zonetwo = gp.Workspace + "\\zone2" #allocation zones that connect the HUCs
rgzonetwo = gp.Workspace + "\\rgzonetwo" #region grouped zonetwo to do the sampling
adjtable = gp.Workspace + "\\adjzone.dbf" # holds HUC adjacency relationships
#############################################################################

#############################################################################
#       IMPORTANT INFORMANTION                   ############################
#   Need to add the addXY command to the points FC to print out x,y coords  #
#############################################################################


# Select HUCs that contain photos
gp.AddMessage(" ")
gp.AddMessage("selecting HCUs with photos")
gp.AddMessage(" ")
gp.MakeFeatureLayer_management(HUCfeat, 'HUC_lyr')
gp.SelectLayerByLocation_management('HUC_lyr', 'intersect', photoPTS)

gp.AddMessage("Building photo HUC feature class")
gp.AddMessage(" ")
gp.CopyFeatures_management(HUCfeat, photoHUCs)

# intersect photo points with HUCs
gp.AddMessage("Intersecting photo points with HUCs")
gp.AddMessage(" ")
inFeatures = [photoPTS, HUCfeat]
clusterTolerance = .5    
gp.Intersect_analysis(inFeatures, interHUC_pts, "", clusterTolerance, "point")

#get unique HUC codes to loop through
gp.AddMessage("Finding unique HUC codes")
gp.AddMessage(" ")
HUCtable = gp.Workspace + "\\hucs.dbf"
statsFields = [["GRIDCODE", "COUNT"]]
#gp.Statistics_analysis(HUCtable, summaryHUC, statsFields)
#gp.Frequency_analysis(HUCtable, summaryHUC, 'GRIDCODE')
gp.Frequency_analysis(interHUC_pts + ".dbf", summaryHUC, 'GRIDCODE')

# Find what watersheds are adjacent to each other
arcpy.PolygonToRaster_conversion(photoHUCs, "GRIDCODE", HUCraster, "", "", "10")
arcpy.env.extent = HUCraster
#use moving window analysis to find adjacent HUCs
#gp.FocalStatistics_sa(HUCraster, HUCVariety, "CIRCLE", "3", "CELL", "VARIETY", "NODATA")
gp.FocalStatistics_sa(HUCraster, HUCVariety, "Circle 3 CELL", "VARIETY", "DATA")
#outFocalStat = FocalStatistics(HUCraster, "NbrCircle(3 CELL)", "VARIETY", "NODATA")
#outFocalStat.save(HUCVariety) 

#pull out variety values greater than 2 to find intersections
gp.RasterCalculator_sa('Con("' + HUCVariety + '" > 2, 1)', varetygt)


#extent varetygt zones by 30 meters
eucAllocate = EucAllocation(varetygt, "30", "", "", "", "", "")
eucAllocate.save(VARAllo)

#create pipeline envelope to mask out the rest of the analysis to weed out allocation boundaries that are not connected via pipeline.
pipe_mask = gp.Workspace + "\\pipe_mask"
gp.EucAllocation_sa(photoPTS, pipe_mask, "30", "", "10", "FID", "", "")
arcpy.env.mask = pipe_mask

#pull out zones that have a value of 2 and mask with the VARAllo to build zones to find connections
gp.RasterCalculator_sa('Con(IsNull("' + VARAllo + '"), Con("' + HUCVariety + '" == 2, 1))', zonetwo)


# region group zonetwo to create unique zones to determine connectivity
gp.RegionGroup_sa(zonetwo, rgzonetwo, "FOUR", "WITHIN", "NO_LINK", "")

#execute  zone statistics to find HUC adjacency
#gp.ZonalStatisticsAsTable_sa(rezonetwo, "VALUE", HUCraster, adjtable, "NODATA", "ALL")
gp.Sample(HUCraster, rgzonetwo, adjtable, "NEAREST")

summarytable = gp.Workspace + "sumsample.dbf"
# Process: Table Select
arcpy.TableSelect_analysis(adjtable, summarytable, "\"hucras\" <> -9999")

adjtable = gp.Workspace + "\\adjsummary.dbf"
# Process: Summary Statistics 
arcpy.Statistics_analysis(summarytable, adjtable, "hucras MIN;hucras MAX", "rgzonetwo")

#sort table to find adjacent HUCs
sort_adjhuc = gp.Workspace + "\\sort_adjhuc.dbf"
gp.Sort_management(adjtable, sort_adjhuc, "MIN_hucras DESCENDING", "UR")


#gp.Addmessage(str(zoneList))



#sort table to find adjacent HUCs
gp.AddMessage(" ")
gp.AddMessage("Finding optimal HUC subsets")
gp.AddMessage(" ")
sort_adjhuc = gp.Workspace + "\\sort_adjhuc2.dbf"
gp.Sort_management(adjtable, sort_adjhuc, "FREQUENCY DESCENDING", "UR")
adjtable = gp.Workspace + "\\adjsummary.dbf"
rows = gp.SearchCursor(sort_adjhuc)
row = rows.Next()
groupList = []
while row:
	tempList = []
	tempList2 = []
	tempIndexList = []
	cnt = 0
	querystring = "MIN_hucras = " + str(row.GetValue("MIN_hucras"))
	rows2 = gp.SearchCursor(adjtable, querystring)
	row2 = rows2.Next()
	tempList.append(str(row.GetValue("MIN_hucras")))
	#gp.AddMessage("From feature = " + str(row.GetValue("MIN_hucras")))
	#This loop populates all first order neighbors to the focus HUC
	while row2:
		if row2.GetValue("MIN_hucras") <> row2.GetValue("MAX_hucras"):
			toExists = row2.GetValue("MAX_hucras") in tempList
			if toExists == 0:
				#gp.AddMessage("    "  + str(row2.GetValue("MAX_hucras")))
				tempList.append(str(row2.GetValue("MAX_hucras")))
				tempList2.append(str(row2.GetValue("MAX_hucras")))
		row2 = rows2.Next()	
	querystring = "MAX_hucras = " + str(row.GetValue("MIN_hucras"))
	rows2 = gp.SearchCursor(adjtable, querystring)
	row2 = rows2.Next()
	#gp.AddMessage("From feature = " + str(row.GetValue("MAX_hucras")))
	while row2:
		if row2.GetValue("MIN_hucras") <> row2.GetValue("MAX_hucras"):
			toExists = row2.GetValue("MIN_hucras") in tempList
			if toExists == 0:
				#gp.AddMessage("    "  + str(row2.GetValue("MAX_hucras")))
				tempList.append(str(row2.GetValue("MIN_hucras")))
				tempList2.append(str(row2.GetValue("MIN_hucras")))
		row2 = rows2.Next()			
		 
	tempList.append("2order")
	#gp.AddMessage(str(tempList))
	cnt1 = 0	
	
	#This loop loops through all first order HUC and populates second order relationiships
	for feature in tempList2:
		if cnt1 == 0:
			if feature <> "2order":
				#tempFeat = feature.split(",")
				querystring = "MIN_hucras = " + str(feature)
				#gp.AddMessage(querystring)
				rows2 = gp.SearchCursor(adjtable, querystring)
				row2 = rows2.Next()
				while row2:
					if row2.GetValue("MIN_hucras") <> row2.GetValue("MAX_hucras"):
						toExists = row2.GetValue("MAX_hucras") in tempList
						if toExists == 0:
							#gp.AddMessage("    "  + str(row2.GetValue("MAX_hucras")))
							tempList.append(str(feature) + ","+ str(row2.GetValue("MAX_hucras")))
					row2 = rows2.Next()
				querystring = "MAX_hucras = " + str(feature)
				rows2 = gp.SearchCursor(adjtable, querystring)
				row2 = rows2.Next()
				while row2:
					if row2.GetValue("MAX_hucras") <> row2.GetValue("MIN_hucras"):
						toExists = row2.GetValue("MIN_hucras") in tempList
						if toExists == 0:
							#gp.AddMessage("    "  + str(row2.GetValue("MAX_hucras")))
							tempList.append(str(feature) + "," + str(row2.GetValue("MIN_hucras")))
					row2 = rows2.Next()
			else:
				cnt1 = 1

	#gp.AddMessage("")
	#gp.AddMessage(str(tempList))
	#gp.AddMessage(" ")
	groupList.append(tempList)
	row = rows.Next()
	
dissList = []
processedList = []
gt100List = []
# This loop finds all neighbors optimizing on number of points and groups by list
gp.AddMessage("Finding Optimized HUC neighbors")
gp.AddMessage(" ")
for list in groupList:
	sumvalue = 0
	tempList = []
	oneorderList = []
	skip = 0
	for feature in list:
		if skip == 0:
			if feature <> "2order":
				proExists = feature in processedList
				if proExists == 0:
					#gp.AddMessage("skip value: " + str(skip))
					querystring = "GRIDCODE = " + str(feature)
					#gp.AddMessage("before 2order " + querystring)
					rows2 = gp.SearchCursor(summaryHUC, querystring)
					row2 = rows2.Next()
					sumvalue = sumvalue + row2.GetValue("FREQUENCY")
					#gp.AddWarning("sumavalue: " + str(sumvalue))
					if sumvalue < 1100:
						tempList.append(feature)
						oneorderList.append(feature)
						processedList.append(feature)
					else:
						sumvalue = sumvalue - row2.GetValue("FREQUENCY")
			else:
				skip = 1
		else:
			if sumvalue < 1100:
				feat = feature.split(",")
				featExists = feat[0] in oneorderList
				proExists = feat[1] in processedList
				if featExists > 0:
					if proExists == 0:
						querystring = "GRIDCODE = " + str(feat[1])
						#gp.AddMessage("after 2order " + querystring)
						rows2 = gp.SearchCursor(summaryHUC, querystring)
						row2 = rows2.Next()
						sumvalue = sumvalue + row2.GetValue("FREQUENCY")
						#gp.AddWarning("sumavalue: " + str(sumvalue))
						if sumvalue < 1100:
							tempList.append(feat[1])
							processedList.append(feat[1])
						else:
							sumvalue = sumvalue - row2.GetValue("FREQUENCY")
			
	#gp.AddMessage(str(tempList))
	gp.AddMessage("")
	dissList.append(tempList)
	
## add dissolve field to lump hucs based on point count and adjacency
gp.AddField_management(photoHUCs, "diss", "LONG")
gp.CalculateField_management(photoHUCs, "diss", "0") # calculate diss (dissolve) to 0

gp.AddMessage("Clustering HUCs into optimized units")
gp.AddMessage(" ")
count = 1
#this loop loops through all lists in the dissList and populates the diss field with a group number (count)
for subList in dissList:
	for feat in subList:
		querystring = "GRIDCODE = " + str(feat)
		rows = gp.UpdateCursor(photoHUCs, querystring)
		row = rows.Next()
		row.SetValue("diss", count)
		rows.UpdateRow(row)
	count = count + 1


#dissolve photoHUCs on diss code that will be the HUC clusters
diss_huc = gp.Workspace + "\\diss_huc.shp"
gp.Dissolve_management(photoHUCs, diss_huc, "diss", "", "SINGLE_PART", "DISSOLVE_LINES")

sort_photo_dbf = gp.Workspace + "\\diss_huc1.dbf"
gp.Sort_management(diss_huc, sort_photo_dbf, "diss DESCENDING", "UR")

rows = gp.SearchCursor(sort_photo_dbf) # this search cursor is to loop through all points and get attributes
row = rows.Next()
gp.AddMessage("Generating point clusters")
gp.AddMessage(" ")
count = 0
#gp.AddMessage("group,xval,yval")
while row: # Loop through the features selected by the search query
    buffHUC = gp.Workspace + "\\buffhuc" + str(count) + ".shp"
    buffHUC_50m = gp.Workspace + "\\buffhuc50" + str(count) + ".shp"
    intersect_photo = gp.Workspace + "\\intphoto" + str(count)
    clipphoto = gp.Workspace + "\\cliphoto" + str(count) + ".shp"
    where_clause = "diss = " + str(row.GetValue("diss"))
    gp.Select_analysis(diss_huc, buffHUC, where_clause)
    #buffer selected set
    buffDist = "50 meters"
    gp.Buffer_analysis(buffHUC, buffHUC_50m, buffDist)
    inFeatures = [photoPTS, buffHUC_50m]
    clusterTolerance = .5    
    gp.Intersect_analysis(inFeatures, intersect_photo, "", clusterTolerance, "point")
    rows2 = gp.SearchCursor(intersect_photo + ".dbf")  # loop through the point inside the buffered HUC
    row2 = rows2.Next()
    while row2:
        xval = str(row2.GetValue("POINT_X"))
        yval = str(row2.GetValue("POINT_Y"))
        string = str(count) + "," + xval + "," + yval
        print >>ofh, string
        #gp.AddMessage(string)
        row2 = rows2.Next()
    count = count + 1
    row = rows.Next()
ofh.close()
gp.AddMessage("Processing Temp. Groupings")
gp.MakeXYEventLayer_management(TempXYFile, "xval", "yval", "tempPTS", photoPTS)
tempLayer = gp.Workspace + "\\tempgroup.shp"
gp.AddMessage("Creating Temp. Group shapefile")
gp.CopyFeatures_management("tempPTS", tempLayer)


gp.AddWarning("######################################")
gp.AddWarning("####          Finished          ######")
gp.AddWarning("######################################")

gp.AddMessage(whatever)
