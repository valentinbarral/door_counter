#!/usr/bin/env python

import rospy
from geometry_msgs.msg import PointStamped, Point
from sensor_msgs.msg import PointCloud2, PointField
import sensor_msgs.point_cloud2 as pc2
from std_msgs.msg import Header
import tf2_ros
import tf2_geometry_msgs
from std_msgs.msg import ColorRGBA, Float32
from jsk_rviz_plugins.msg import OverlayText
import json

from grid_occupancy import  OccupancyGrid, TargetPoint, GridSize, TimeOccupancyHandler, TimeOccupancyHandlerOptions, ZoneOfInterest

if __name__ == "__main__":

    rospy.init_node('TimeOccupancyNode', anonymous=True)
    rate = rospy.Rate(5)  # hz
    target_positions_topic = rospy.get_param('~target_positions_topic')
    grid_width = float(rospy.get_param('~grid_width'))
    grid_height = float(rospy.get_param('~grid_height'))
    zones_of_interest = rospy.get_param('~zones_of_interest')


    grid_size = GridSize(width_meters=grid_width, height_meters=grid_height)
    reduce_fun = lambda time_elapsed: time_elapsed * 10
    expansion_fun = lambda num_cells: 50/(num_cells +1)
    options = TimeOccupancyHandlerOptions(reduce_fun=reduce_fun, expansion_fun=expansion_fun, 
    min_expansion_threshold=20, delete_threshold=10, max_cost=150, 
    occupancy_cost_threshold=1300, occupancy_time=2, deoccupancy_time=5, max_occupancy_time=5)
    time_occupancy_handler = TimeOccupancyHandler(options=options, grid_size=grid_size)

    zones = json.loads(str(zones_of_interest))

    zones_list = zones['zones']

    for zone in zones_list:
        time_occupancy_handler.addOccupancyZone(ZoneOfInterest(zone['x'], zone['y'], zone['width'], zone['height'], zone['id']))    


    #Points of each zone (to show in rviz)
    example_occupancy_grid = OccupancyGrid(grid_size.width, grid_size.height)

    for zone in time_occupancy_handler.occupancy_zones.values():
        example_occupancy_grid.addZoneOfInterest(zone)

    
    cloud_points = []
    color_inc = int(100/len(example_occupancy_grid.zones_of_interest.values()))
    i = 0
    for zone in example_occupancy_grid.zones_of_interest.values():
        zone_points = example_occupancy_grid.getGridPositionsOfZone(zone.id)
        for tp in zone_points:
            cloud_points.append([tp.x, tp.y, 0, i*color_inc])
        i = i+1
    
    header_point_cloud = Header()
    header_point_cloud.frame_id = "grid"
    fields_point_cloud =  [
        PointField('x', 0, PointField.FLOAT32, 1),
        PointField('y', 4, PointField.FLOAT32, 1),
        PointField('z', 8, PointField.FLOAT32, 1),
        PointField('cost', 12, PointField.FLOAT32, 1 ),]

    pub_ref_grid = rospy.Publisher('/gtec/time_occupancy/ref_grid', PointCloud2, queue_size=100)
    pub_overlay_text = rospy.Publisher('/gtec/time_occupancy/text', OverlayText, queue_size=100)

    tf_buffer = tf2_ros.Buffer(rospy.Duration(3.0)) #tf buffer length
    tf_listener = tf2_ros.TransformListener(tf_buffer)
    transform = tf_buffer.lookup_transform("grid",
                                   "map", #source frame
                                   rospy.Time(0), #get the tf at first available time
                                   rospy.Duration(1.0))
  
    def getTransformedPoint(point_msg, id):
        tf_pos = tf2_geometry_msgs.do_transform_point(point_msg, transform)
        return TargetPoint(tf_pos.point.x, tf_pos.point.y, tf_pos.point.z, 0, id)

    pubs_grid = {}
    for n in range(8):
        a_pub = rospy.Publisher('/gtec/time_ocuppancy/'+str(n), PointCloud2, queue_size=100)
        pubs_grid[n] = a_pub
        pos_handler = lambda n: lambda pos: time_occupancy_handler.addPosition(getTransformedPoint(pos,n))
        rospy.Subscriber(str(target_positions_topic)+'/'+str(n), PointStamped, pos_handler(n))  

    print("=========== GTEC Occupancy Node ============")

    text_msg = OverlayText()
    text_msg.width = 400
    text_msg.height = 600
    #text.height = 600
    text_msg.left = 10
    text_msg.top = 10
    text_msg.text_size = 18
    text_msg.line_width = 2
    text_msg.font = "DejaVu Sans Mono"
    text_msg.fg_color = ColorRGBA(25 / 255.0, 1.0, 240.0 / 255.0, 1.0)
    text_msg.bg_color = ColorRGBA(0.0, 0.0, 0.0, 0.2)


    while not rospy.is_shutdown():
        header_point_cloud.stamp = rospy.Time.now()
        point_cloud_grid = pc2.create_cloud(header_point_cloud, fields_point_cloud, cloud_points)
        pub_ref_grid.publish(point_cloud_grid)

        for oc_grid_id in time_occupancy_handler.occupancy_grids.keys():
            oc_grid = time_occupancy_handler.occupancy_grids[oc_grid_id]
            grid_points = oc_grid.getGridPositions()
            cloud_points_grid = []
            for tp in grid_points:
                cloud_points_grid.append([tp.x, tp.y, 0, tp.z]) #Cost is in z value
            header_point_cloud.stamp = rospy.Time.now()
            point_cloud_grid = pc2.create_cloud(header_point_cloud, fields_point_cloud, cloud_points_grid)
            pubs_grid[oc_grid_id].publish(point_cloud_grid)
            
        list_targets_in_zones = time_occupancy_handler.loop()

        text = ''
        text_by_zone = {}
        for zone in example_occupancy_grid.zones_of_interest.values():
            text_by_zone[zone.id] = f'Zone {zone.id}: [ '

        for (zone_id, target_id) in list_targets_in_zones:
            text_by_zone[zone.id] = text_by_zone[zone.id] + f'{target_id} '

        for zone in example_occupancy_grid.zones_of_interest.values():
            text_by_zone[zone.id] = text_by_zone[zone.id] + ']\n'
            text = text + text_by_zone[zone.id]
        
        text_msg.text = text
        pub_overlay_text.publish(text_msg)

        rate.sleep()