PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE disaster_report (
	id INTEGER NOT NULL, 
	task_id VARCHAR(20) NOT NULL, 
	disaster_type VARCHAR(50) NOT NULL, 
	severity VARCHAR(20) NOT NULL, 
	lat FLOAT NOT NULL, 
	lon FLOAT NOT NULL, 
	location VARCHAR(100) NOT NULL, 
	full_address VARCHAR(200) NOT NULL, 
	resources VARCHAR(200), 
	constraints VARCHAR(200), 
	status VARCHAR(20), 
	priority INTEGER, 
	date_submitted DATETIME, 
	assigned_team VARCHAR(50), 
	date_str VARCHAR(20), 
	day_str VARCHAR(20), 
	time_str VARCHAR(20), 
	affected VARCHAR(50), 
	response_type VARCHAR(50), 
	notes TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (task_id)
);
INSERT INTO disaster_report VALUES(1,'TASK-001','Typhoon','Low',14.772135000000000459,121.02542099999999435,'Meycauayan','Bagong Silang River','Ambulance','Flooded Route','Resolved',1,'2026-05-04 03:59:35.578291','TM-001','05/04/2026','Monday','11:59 AM','1-10','Rescue','');
INSERT INTO disaster_report VALUES(2,'TASK-002','Fire','Medium',14.796101000000000169,120.928957699999998,'Bocaue','J. P. Rizal Street','Ambulance, Fire Truck','','Pending',1,'2026-05-04 04:01:33.526666',NULL,'05/04/2026','Monday','12:00 PM','11-50','Firefighting','');
CREATE TABLE team (
	id INTEGER NOT NULL, 
	team_id VARCHAR(20) NOT NULL, 
	name VARCHAR(50) NOT NULL, 
	leader VARCHAR(50), 
	role VARCHAR(50), 
	status VARCHAR(20), 
	lat FLOAT, 
	lon FLOAT, 
	last_updated DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (team_id)
);
INSERT INTO team VALUES(1,'TM-001','TM-001','Cee Jay','Response Unit','Available',14.772135000000000459,121.02542099999999435,'2026-05-04 14:13:27.617648');
CREATE TABLE user (
	id INTEGER NOT NULL, 
	account_id VARCHAR(50) NOT NULL, 
	password VARCHAR(100) NOT NULL, 
	role VARCHAR(20), 
	first_name VARCHAR(50), 
	last_name VARCHAR(50), 
	phone VARCHAR(20), 
	status VARCHAR(20), 
	last_login DATETIME, email VARCHAR(120) DEFAULT '', 
	PRIMARY KEY (id), 
	UNIQUE (account_id)
);
INSERT INTO user VALUES(1,'programmer','password123','Programmer','Dev','Admin','09XX XXX XXXX','Active','2026-05-04 21:49:33.499342','');
INSERT INTO user VALUES(2,'admin','password123','Admin','System','Admin','09XX XXX XXXX','Active','2026-05-04 22:11:19.946138','');
INSERT INTO user VALUES(3,'OPT-001','password001','Operator','Vin','Cent','09560414207','Active','2026-05-04 23:51:18.314977','onikabutosan@gmail.com');
INSERT INTO user VALUES(4,'RSP-001','password001','Responder','Cee','Jay','09560414207','Active','2026-05-04 14:13:27.608021','czerina.abendanio@gmail.com');
CREATE TABLE road_constraint (
	id INTEGER NOT NULL, 
	node_name VARCHAR(100) NOT NULL, 
	reason VARCHAR(255), 
	is_active BOOLEAN, 
	timestamp DATETIME, 
	PRIMARY KEY (id)
);
INSERT INTO road_constraint VALUES(1,'San Miguel','Flood',0,'2026-04-21 05:51:40.594569');
INSERT INTO road_constraint VALUES(2,'San Miguel','Flood',0,'2026-04-21 05:55:58.118419');
INSERT INTO road_constraint VALUES(3,'San Miguel (Viola St)','Flood',0,'2026-04-21 05:59:31.714652');
INSERT INTO road_constraint VALUES(4,'Malolos (City Hall)','Flood',0,'2026-04-21 06:16:35.821827');
INSERT INTO road_constraint VALUES(5,'Hagonoy','Flood',0,'2026-04-21 06:16:45.406300');
INSERT INTO road_constraint VALUES(6,'San Miguel (Viola St)','Flood',0,'2026-04-21 06:16:52.453866');
INSERT INTO road_constraint VALUES(7,'San Miguel','Flood',0,'2026-04-21 06:26:17.024807');
INSERT INTO road_constraint VALUES(8,'De Leon Sr. Street','Unknown: flood',0,'2026-04-21 07:21:10.581518');
INSERT INTO road_constraint VALUES(9,'Viola Street','Unknown: earth',0,'2026-04-21 07:23:32.567530');
INSERT INTO road_constraint VALUES(10,'Sempio Street','San Miguel: flooded',0,'2026-04-21 07:41:25.685399');
INSERT INTO road_constraint VALUES(11,'De Leon Sr. Street','San Miguel: flood',0,'2026-04-21 07:59:01.682098');
INSERT INTO road_constraint VALUES(12,'De Leon Street','San Miguel: flood',0,'2026-04-21 07:59:10.402101');
INSERT INTO road_constraint VALUES(13,'De Leon Street','San Miguel: flood',0,'2026-04-21 07:59:19.069617');
INSERT INTO road_constraint VALUES(14,'De Leon Street','San Miguel: flood',0,'2026-04-21 07:59:29.005277');
INSERT INTO road_constraint VALUES(15,'De Leon Sr. Street','San Miguel: flood',0,'2026-04-21 08:12:20.027229');
INSERT INTO road_constraint VALUES(16,'De Leon Street','San Miguel: flood',0,'2026-04-21 08:12:30.894706');
INSERT INTO road_constraint VALUES(17,'De Leon Street','San Miguel: flood',0,'2026-04-21 08:12:36.685681');
INSERT INTO road_constraint VALUES(18,'De Leon Street','San Miguel: flood',0,'2026-04-21 08:12:44.203185');
INSERT INTO road_constraint VALUES(19,'Macabebe-Calumpit-Apalit Road','San Miguel: flood',0,'2026-04-21 08:12:54.093990');
INSERT INTO road_constraint VALUES(20,'Viola Street','San Miguel: flood',0,'2026-04-21 08:26:37.550826');
INSERT INTO road_constraint VALUES(21,'Cagayan Valley Road','San Miguel: flood',0,'2026-04-21 08:27:01.904231');
INSERT INTO road_constraint VALUES(22,'Viola Street','San Miguel: flood',0,'2026-04-21 08:27:18.309064');
INSERT INTO road_constraint VALUES(23,'Viola Street','San Miguel: flooded',0,'2026-04-21 08:33:06.451583');
INSERT INTO road_constraint VALUES(24,'Viola Street','San Miguel: flood',0,'2026-04-21 08:39:02.317216');
INSERT INTO road_constraint VALUES(25,'Nemarville 2','San Miguel: flood',0,'2026-04-21 08:39:18.793564');
INSERT INTO road_constraint VALUES(26,'Viola Street','San Miguel: flood',0,'2026-04-21 08:39:29.044490');
INSERT INTO road_constraint VALUES(27,'Cagayan Valley Road','San Miguel: earthquake',0,'2026-04-21 08:39:45.878170');
INSERT INTO road_constraint VALUES(28,'Viola Street','San Miguel: flooded',0,'2026-04-21 08:45:16.487942');
INSERT INTO road_constraint VALUES(29,'Viola Street','San Miguel: flooded',0,'2026-04-21 08:46:46.895353');
INSERT INTO road_constraint VALUES(30,'Cagayan Valley Road','San Miguel: flooded',0,'2026-04-21 08:47:27.291147');
INSERT INTO road_constraint VALUES(31,'Cagayan Valley Road','San Miguel: flooded',0,'2026-04-21 08:47:50.206350');
INSERT INTO road_constraint VALUES(32,'Viola Street','San Miguel: flooded',0,'2026-04-21 08:48:05.613661');
INSERT INTO road_constraint VALUES(33,'Viola Street','San Miguel: flood',0,'2026-04-21 08:48:15.520304');
INSERT INTO road_constraint VALUES(34,'Unknown Area','San Miguel: flooded',0,'2026-04-21 08:50:45.833629');
INSERT INTO road_constraint VALUES(35,'Viola Street','San Miguel: flooded',0,'2026-04-21 08:50:53.795354');
INSERT INTO road_constraint VALUES(36,'Cagayan Valley Road','San Miguel: flooded',0,'2026-04-21 08:51:13.786908');
INSERT INTO road_constraint VALUES(37,'Viola Street','San Miguel: flooded',0,'2026-04-21 08:52:02.762246');
INSERT INTO road_constraint VALUES(38,'Cagayan Valley Road','San Miguel: flooded',0,'2026-04-21 08:52:35.512006');
INSERT INTO road_constraint VALUES(39,'Viola Street','San Miguel: flooded',0,'2026-04-21 08:56:32.154139');
INSERT INTO road_constraint VALUES(40,'Cagayan Valley Road','San Miguel: flooded',0,'2026-04-21 08:57:02.443476');
INSERT INTO road_constraint VALUES(41,'Viola Street','San Miguel: flood',1,'2026-04-21 09:06:38.146798');
INSERT INTO road_constraint VALUES(42,'Cagayan Valley Road','San Miguel: f',1,'2026-04-21 09:07:14.247715');
INSERT INTO road_constraint VALUES(43,'Viola Street','San Miguel: flood',1,'2026-04-21 09:12:35.583156');
CREATE TABLE route_log (
	id INTEGER NOT NULL, 
	task_id VARCHAR(20), 
	origin VARCHAR(100) NOT NULL, 
	destination VARCHAR(100) NOT NULL, 
	new_distance FLOAT, 
	reason VARCHAR(255), 
	status VARCHAR(50) NOT NULL, 
	timestamp DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE notification (
	id INTEGER NOT NULL, 
	task_id VARCHAR(20) NOT NULL, 
	message VARCHAR(255) NOT NULL, 
	is_read BOOLEAN, 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
INSERT INTO notification VALUES(1,'TASK-001','🚨 TASK-001 — Team is En Route to San Miguel. Update status when task is complete.',1,'2026-04-26 07:16:11.690039');
INSERT INTO notification VALUES(2,'TASK-001','✅ TASK-001 — Responder has ended task at San Miguel. Please update the report status.',1,'2026-04-26 07:16:16.383083');
INSERT INTO notification VALUES(3,'TASK-001','🚨 TASK-001 — Team is En Route to San Miguel. Update status when task is complete.',1,'2026-04-26 07:22:48.056433');
INSERT INTO notification VALUES(4,'TASK-001','✅ TASK-001 — Responder has ended task at San Miguel. Please update the report status.',1,'2026-04-26 07:22:51.478716');
INSERT INTO notification VALUES(5,'TASK-001','🚨 TASK-001 — Team is En Route to San Miguel. Update status when task is complete.',1,'2026-04-26 07:25:49.501516');
INSERT INTO notification VALUES(6,'TASK-001','✅ TASK-001 — Responder has ended task at San Miguel. Please update the report status.',1,'2026-04-26 07:25:54.393905');
INSERT INTO notification VALUES(7,'TASK-003','🚨 TASK-003 — Team is En Route to Meycauayan. Update status when task is complete.',1,'2026-04-26 07:34:53.348306');
INSERT INTO notification VALUES(8,'TASK-003','✅ TASK-003 — Responder has ended task at Meycauayan. Please update the report status.',1,'2026-04-26 07:34:58.239874');
INSERT INTO notification VALUES(9,'TASK-002','🚨 TASK-002 — Team is En Route to San Miguel. Update status when task is complete.',1,'2026-04-26 07:39:20.353407');
INSERT INTO notification VALUES(10,'TASK-004','🚨 TASK-004 — Team is En Route to Meycauayan. Update status when task is complete.',1,'2026-04-26 13:08:05.582203');
INSERT INTO notification VALUES(11,'TASK-004','✅ TASK-004 — Responder has ended task at Meycauayan. Please update the report status.',1,'2026-04-26 13:11:53.263775');
INSERT INTO notification VALUES(12,'TASK-002','TASK-002 — Team is En Route to San Miguel. Update status when task is complete.',1,'2026-04-27 03:12:17.580961');
INSERT INTO notification VALUES(13,'TASK-002','TASK-002 — Responder has ended task at San Miguel. Please update the report status.',1,'2026-04-27 03:12:50.205381');
INSERT INTO notification VALUES(14,'TASK-001','TASK-001 — Team is En Route to Meycauayan. Update status when task is complete.',0,'2026-05-04 13:45:14.705062');
INSERT INTO notification VALUES(15,'TASK-001','TASK-001 — Responder has ended task at Meycauayan. Please update the report status.',0,'2026-05-04 13:47:00.295555');
COMMIT;
