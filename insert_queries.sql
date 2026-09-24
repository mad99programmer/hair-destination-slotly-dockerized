INSERT INTO businesses
    (name, phone, email, website, description, is_active)
VALUES
    (
        'Hair Destination Studio',
        '+918828381386',
        'hairdestinationstudio@gmail.com',
        'https://hairdestinationstudio.in/',
        'Hair Destination Studio',
        TRUE
    );

INSERT INTO branches
    (
        business_id,
        name,
        address,
        maps_url,
        phone,
        email,
        slot_duration_minutes,
        capacity,
        is_active
    )
VALUES
    (
        1,
        'Powai',
        '611, 6th Floor, Gateway Plaza, Central Ave, Hiranandani Gardens, Powai, Mumbai, Maharashtra 400076',
        NULL,
        '+918828381386',
        'hairdestinationstudio@gmail.com',
        60,
        3,
        TRUE
    );
INSERT INTO branches
    (
        business_id,
        name,
        address,
        maps_url,
        phone,
        email,
        slot_duration_minutes,
        capacity,
        is_active
    )
VALUES
    (
        1,
        'Malad',
        'Solitaire 1, Shop No. 310, 3rd Floor, New Link Rd, Opp. Infinity Mall, Malad West, Mumbai, Maharashtra 400064',
        NULL,
        '+918828381386',
        'hairdestinationstudio@gmail.com',
        60,
        3,
        TRUE
    );

INSERT INTO branch_working_hours
    (branch_id, weekday, start_time, end_time, is_active)
VALUES
    (1, 'Monday',    '10:00:00', '20:00:00', TRUE),
    (1, 'Tuesday',   '10:00:00', '20:00:00', TRUE),
    (1, 'Wednesday', '10:00:00', '20:00:00', TRUE),
    (1, 'Thursday',  '10:00:00', '20:00:00', TRUE),
    (1, 'Friday',    '10:00:00', '20:00:00', TRUE),
    (1, 'Saturday',  '10:00:00', '20:00:00', TRUE),
    (1, 'Sunday',    '10:00:00', '20:00:00', TRUE);
INSERT INTO branch_working_hours
    (branch_id, weekday, start_time, end_time, is_active)
VALUES
    (2, 'Monday',    '10:00:00', '20:00:00', TRUE),
    (2, 'Tuesday',   '10:00:00', '20:00:00', TRUE),
    (2, 'Wednesday', '10:00:00', '20:00:00', TRUE),
    (2, 'Thursday',  '10:00:00', '20:00:00', TRUE),
    (2, 'Friday',    '10:00:00', '20:00:00', TRUE),
    (2, 'Saturday',  '10:00:00', '20:00:00', TRUE),
    (2, 'Sunday',    '10:00:00', '20:00:00', TRUE);

INSERT INTO services
    (business_id, name, description, duration_minutes, price, is_active)
VALUES
    (
        1,
        'Consultation',
        'Hair consultation',
        30,
        NULL,
        TRUE
    ),
    (
        1,
        'Monthly Maintenance',
        'Monthly hair system maintenance',
        60,
        NULL,
        TRUE
    );

INSERT INTO services
    (business_id, name, description, duration_minutes, price, is_active)
VALUES
    (
        2,
        'Consultation',
        'Hair consultation',
        30,
        NULL,
        TRUE
    ),
    (
        2,
        'Monthly Maintenance',
        'Monthly hair system maintenance',
        60,
        NULL,
        TRUE
    );